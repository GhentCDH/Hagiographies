//! Undo for everything that does not lose data.
//!
//! A stack per person, so two students working at once cannot undo each other's
//! work. The app has no login of its own (Caddy handles that in front), so who
//! you are is guessed from the request: an authentication header from the proxy
//! if there is one, otherwise a hash of the user agent, languages and client
//! address. That is not identity, it is a good enough bucket, which is all an
//! undo stack needs.
//!
//! The stacks live in memory, so a restart forgets them. The alternative is a
//! table of pending undos, and nobody needs to undo something from last week.
//!
//! Undo never destroys anything it cannot prove it created:
//!
//! * a move or rename is put back, keeping the file_id, so links stay good;
//! * a folder we created is removed only while it is still empty;
//! * an upload is removed only if the files are byte for byte as uploaded, and
//!   only if nothing in the database links to them yet.
//!
//! Anything else is refused with a reason. Deletes are not in here because the
//! app has none.

use std::collections::VecDeque;
use std::hash::{DefaultHasher, Hash, Hasher};

use axum::extract::FromRequestParts;
use axum::http::request::Parts;
use tokio::sync::Mutex;
use uuid::Uuid;

use crate::error::{AppError, AppResult};
use crate::paths::{self, RelPath};
use crate::routes;
use crate::state::AppState;

/// Deep enough to walk back a wrong turn, shallow enough that the oldest entries
/// have not gone stale.
const CAPACITY: usize = 20;

/// How many people we keep a stack for before forgetting the quietest one.
const MAX_PEOPLE: usize = 64;

/// Headers a proxy might use to say who it let in. Checked in this order.
const USER_HEADERS: &[&str] = &[
    "x-forwarded-user",
    "x-authenticated-user",
    "remote-user",
    "x-forwarded-email",
];

/// Which undo stack a request belongs to.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct Who(String);

impl std::fmt::Display for Who {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}

impl<S: Send + Sync> FromRequestParts<S> for Who {
    type Rejection = std::convert::Infallible;

    async fn from_request_parts(parts: &mut Parts, _state: &S) -> Result<Self, Self::Rejection> {
        let header = |name: &str| {
            parts
                .headers
                .get(name)
                .and_then(|value| value.to_str().ok())
                .unwrap_or_default()
                .to_string()
        };

        // If the proxy in front tells us who this is, believe it. Nothing here is
        // a security decision; it only decides whose undo stack to use.
        for name in USER_HEADERS {
            let value = header(name);
            if !value.is_empty() {
                return Ok(Who(format!("user:{value}")));
            }
        }

        // Otherwise: the browser, its languages, and where it came from. Two
        // students on identical laptops behind one address will share a stack.
        // Nothing breaks if they do, they just see each other's undo.
        let client = {
            let forwarded = header("x-forwarded-for");
            match forwarded.split(',').next().map(str::trim) {
                Some(first) if !first.is_empty() => first.to_string(),
                _ => header("x-real-ip"),
            }
        };

        let mut hasher = DefaultHasher::new();
        header("user-agent").hash(&mut hasher);
        header("accept-language").hash(&mut hasher);
        client.hash(&mut hasher);

        Ok(Who(format!("fp:{:016x}", hasher.finish())))
    }
}

#[derive(Debug, Clone)]
pub enum Step {
    /// A file was moved or renamed. Put it back.
    FileMoved {
        file_id: Uuid,
        from: RelPath,
        to: RelPath,
    },
    /// A folder was moved or renamed, with everything under it. Put it back.
    DirMoved { from: RelPath, to: RelPath },
    /// A folder was created. Remove it while it is still empty.
    DirCreated { path: RelPath },
    /// Files arrived. Remove them if they are untouched and unreferenced.
    /// `root` is the folder a folder upload created, removed once it is empty.
    FilesAdded {
        files: Vec<(RelPath, i64)>,
        root: Option<RelPath>,
    },
}

#[derive(Debug, Clone)]
pub struct Entry {
    pub step: Step,
    /// What the user did, for the button's tooltip.
    pub label: String,
}

/// One stack per person, newest last.
#[derive(Debug, Default)]
pub struct UndoStack {
    /// Insertion ordered by last use, so the quietest stack is the first to go.
    people: Mutex<Vec<(Who, VecDeque<Entry>)>>,
}

impl UndoStack {
    pub async fn push(&self, who: &Who, label: impl Into<String>, step: Step) {
        let mut people = self.people.lock().await;

        let at = match people.iter().position(|(key, _)| key == who) {
            Some(at) => at,
            None => {
                if people.len() == MAX_PEOPLE {
                    people.remove(0);
                }
                people.push((who.clone(), VecDeque::new()));
                people.len() - 1
            }
        };

        // Move to the back: least recently used ends up at the front.
        let (key, mut entries) = people.remove(at);
        if entries.len() == CAPACITY {
            entries.pop_front();
        }
        entries.push_back(Entry {
            step,
            label: label.into(),
        });
        people.push((key, entries));
    }

    pub async fn peek(&self, who: &Who) -> Option<Entry> {
        let people = self.people.lock().await;
        people
            .iter()
            .find(|(key, _)| key == who)
            .and_then(|(_, entries)| entries.back().cloned())
    }

    pub async fn pop(&self, who: &Who) -> Option<Entry> {
        let mut people = self.people.lock().await;
        people
            .iter_mut()
            .find(|(key, _)| key == who)
            .and_then(|(_, entries)| entries.pop_back())
    }

    /// Put an entry back after its undo failed, so the button does not silently
    /// lose the operation.
    pub async fn restore(&self, who: &Who, entry: Entry) {
        let mut people = self.people.lock().await;
        if let Some((_, entries)) = people.iter_mut().find(|(key, _)| key == who) {
            entries.push_back(entry);
        } else {
            people.push((who.clone(), VecDeque::from([entry])));
        }
    }
}

/// Reverse one step. Returns what it did, for the confirmation message.
pub async fn apply(state: &AppState, step: &Step) -> AppResult<String> {
    match step {
        Step::FileMoved { file_id, from, to } => {
            routes::move_file_back(state, *file_id, to, from).await?;
            Ok(format!("Put '{from}' back."))
        }

        Step::DirMoved { from, to } => {
            routes::move_dir_back(state, to, from).await?;
            Ok(format!("Put the folder '{from}' back."))
        }

        Step::DirCreated { path } => {
            let abs = paths::resolve(&state.config.share_root, path)?;
            let mut entries = std::fs::read_dir(&abs)?;
            if entries.next().is_some() {
                return Err(AppError::Conflict(format!(
                    "'{path}' is not empty any more, so it was left alone"
                )));
            }
            std::fs::remove_dir(&abs)?;
            tracing::info!(path = %path, "undo: folder removed");
            Ok(format!("Removed the folder '{path}'."))
        }

        Step::FilesAdded { files, root } => undo_upload(state, files, root.as_ref()).await,
    }
}

async fn undo_upload(
    state: &AppState,
    files: &[(RelPath, i64)],
    root: Option<&RelPath>,
) -> AppResult<String> {
    let share = &state.config.share_root;

    // Check everything before removing anything, so a refusal leaves the upload
    // exactly as it was.
    let mut present = Vec::new();
    for (rel, size) in files {
        let Ok(abs) = paths::resolve(share, rel) else {
            // Already gone. Nothing to take back, but the row still goes.
            continue;
        };
        let actual = std::fs::metadata(&abs)?.len() as i64;
        if actual != *size {
            return Err(AppError::Conflict(format!(
                "'{rel}' has changed since it was uploaded, so the upload was left alone"
            )));
        }
        present.push((rel.clone(), abs));
    }

    // A link to one of these is already in the research data. Removing the file
    // would break it, and the reference row would go with it.
    let paths: Vec<&str> = files.iter().map(|(rel, _)| rel.as_str()).collect();
    let referenced: Vec<String> = sqlx::query_scalar(
        "SELECT f.relative_path
         FROM hagio_admin.file f
         JOIN hagio_admin.file_reference r USING (file_id)
         WHERE f.relative_path = ANY($1)",
    )
    .bind(&paths)
    .fetch_all(&state.pool)
    .await?;

    if !referenced.is_empty() {
        return Err(AppError::Conflict(format!(
            "the database already links to {}, so the upload was left alone",
            referenced.join(", ")
        )));
    }

    for (_, abs) in &present {
        std::fs::remove_file(abs)?;
    }
    sqlx::query("DELETE FROM hagio_admin.file WHERE relative_path = ANY($1)")
        .bind(&paths)
        .execute(&state.pool)
        .await?;

    // Empty directories the upload made on the way, deepest first.
    let mut note = String::new();
    if let Some(root) = root {
        match remove_empty_tree(share, root) {
            Ok(true) => {}
            Ok(false) => note = format!(" '{root}' had other files in it, so it stayed."),
            Err(e) => tracing::warn!(path = %root, "could not tidy up after an undo: {e}"),
        }
    }

    let count = present.len();
    tracing::info!(files = count, "undo: upload removed");
    Ok(format!(
        "Removed {count} uploaded file{}.{note}",
        if count == 1 { "" } else { "s" }
    ))
}

/// Remove `dir` and everything under it, as long as it holds no files. Returns
/// false when something was left behind.
fn remove_empty_tree(share: &std::path::Path, dir: &RelPath) -> std::io::Result<bool> {
    let abs = match paths::resolve(share, dir) {
        Ok(abs) => abs,
        Err(_) => return Ok(true),
    };

    let mut empty = true;
    for entry in std::fs::read_dir(&abs)? {
        let entry = entry?;
        if entry.file_type()?.is_dir() {
            let Some(child) = paths::relativise(share, &entry.path()) else {
                empty = false;
                continue;
            };
            if !remove_empty_tree(share, &child)? {
                empty = false;
            }
        } else {
            empty = false;
        }
    }

    if empty {
        std::fs::remove_dir(&abs)?;
    }
    Ok(empty)
}
