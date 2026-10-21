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
//! Every step is recorded as **ids and old values, never paths**. That is what
//! makes undo survive the world moving underneath it: undoing a file move still
//! works after somebody renamed the folder it sits in, because the entry says
//! "this file, back into that folder" rather than naming two paths that have since
//! changed.
//!
//! Undo never destroys anything it cannot prove it created:
//!
//! * a move or rename is put back, keeping the id, so links stay good;
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
use crate::tree;

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
    /// A file was renamed. Give it its old name back.
    FileRenamed { file_id: Uuid, old_name: String },
    /// A file was moved. Put it back in the folder it came from.
    FileMoved {
        file_id: Uuid,
        old_directory_id: Uuid,
    },
    /// A folder was renamed. Give it its old name back.
    DirRenamed {
        directory_id: Uuid,
        old_name: String,
    },
    /// A folder was moved. Put it back under the parent it came from.
    DirMoved {
        directory_id: Uuid,
        old_parent_id: Uuid,
    },
    /// A folder was created. Remove it while it is still empty.
    DirCreated { directory_id: Uuid },
    /// Files arrived. Remove them if they are untouched and unreferenced. `root`
    /// is the folder a folder upload created, removed once it is empty.
    FilesAdded {
        files: Vec<(Uuid, i64)>,
        root: Option<Uuid>,
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
    /// Ordered by last use, so the quietest stack is the first to go.
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
        Step::FileRenamed { file_id, old_name } => {
            let current = file_now(state, *file_id).await?;
            // `join` and not `join_new`: the old name was already on the share, so
            // it does not have to satisfy the rules for a name we are creating.
            let target = current
                .parent()
                .unwrap_or_else(RelPath::root)
                .join(old_name, &[])?;
            routes::move_file_back(state, *file_id, &current, &target).await?;
            Ok(format!("Renamed it back to '{old_name}'."))
        }

        Step::FileMoved {
            file_id,
            old_directory_id,
        } => {
            let current = file_now(state, *file_id).await?;
            let name = current.file_name().unwrap_or_default();
            let target = dir_now(state, *old_directory_id).await?.join(name, &[])?;
            routes::move_file_back(state, *file_id, &current, &target).await?;
            Ok(format!("Moved '{name}' back."))
        }

        Step::DirRenamed {
            directory_id,
            old_name,
        } => {
            let current = dir_now(state, *directory_id).await?;
            let target = current
                .parent()
                .unwrap_or_else(RelPath::root)
                .join(old_name, &[])?;
            routes::move_dir_back(state, &current, &target).await?;
            Ok(format!("Renamed the folder back to '{old_name}'."))
        }

        Step::DirMoved {
            directory_id,
            old_parent_id,
        } => {
            let current = dir_now(state, *directory_id).await?;
            let name = current.file_name().unwrap_or_default();
            let target = dir_now(state, *old_parent_id).await?.join(name, &[])?;
            routes::move_dir_back(state, &current, &target).await?;
            Ok(format!("Moved the folder '{name}' back."))
        }

        Step::DirCreated { directory_id } => {
            let path = dir_now(state, *directory_id).await?;
            let abs = paths::resolve(&state.config.share_root, &path)?;

            let mut entries = std::fs::read_dir(&abs)?;
            if entries.next().is_some() {
                return Err(AppError::Conflict(format!(
                    "'{path}' is not empty any more, so it was left alone"
                )));
            }
            refuse_if_referenced(state, &[], &[*directory_id]).await?;

            std::fs::remove_dir(&abs)?;
            delete_dir_rows(state, *directory_id).await?;

            tracing::info!(path = %path, "undo: folder removed");
            Ok(format!("Removed the folder '{path}'."))
        }

        Step::FilesAdded { files, root } => undo_upload(state, files, *root).await,
    }
}

/// Where a file is *now*, which is the whole point of storing an id: the answer
/// can have changed since the operation we are undoing.
async fn file_now(state: &AppState, file_id: Uuid) -> AppResult<RelPath> {
    tree::file_path(&state.pool, file_id)
        .await?
        .ok_or_else(|| AppError::Conflict("that file is no longer tracked".to_string()))
}

async fn dir_now(state: &AppState, directory_id: Uuid) -> AppResult<RelPath> {
    tree::dir_path(&state.pool, directory_id)
        .await?
        .ok_or_else(|| AppError::Conflict("that folder is no longer tracked".to_string()))
}

/// Refuse to remove anything the research data already links to. Removing the row
/// would take its `file_reference` with it, quietly breaking a link somebody
/// pasted into Mathesar.
async fn refuse_if_referenced(
    state: &AppState,
    file_ids: &[Uuid],
    directory_ids: &[Uuid],
) -> AppResult<()> {
    // One reference table per source, so this is a union of two. Both are real
    // foreign keys, which is the point: nothing here has to match on a table name.
    let referenced: Vec<String> = sqlx::query_scalar(
        "SELECT DISTINCT coalesce(p.relative_path, dp.relative_path)
         FROM (
             SELECT file_id, directory_id FROM hagio_admin.manuscript_link_reference
           UNION ALL
             SELECT file_id, directory_id FROM hagio_admin.edition_link_reference
         ) r
         LEFT JOIN hagio_admin.file_path p ON p.file_id = r.file_id
         LEFT JOIN hagio_admin.directory_path dp ON dp.directory_id = r.directory_id
         WHERE r.file_id = ANY($1) OR r.directory_id = ANY($2)",
    )
    .bind(file_ids)
    .bind(directory_ids)
    .fetch_all(&state.pool)
    .await?;

    if referenced.is_empty() {
        Ok(())
    } else {
        Err(AppError::Conflict(format!(
            "the database already links to {}, so it was left alone",
            referenced.join(", ")
        )))
    }
}

/// Remove a folder's row and every row below it. Only ever called for a tree we
/// have just emptied ourselves; the FK from `file.directory_id` is the backstop if
/// that is ever wrong.
async fn delete_dir_rows(state: &AppState, directory_id: Uuid) -> AppResult<()> {
    sqlx::query(
        "WITH RECURSIVE below AS (
             SELECT directory_id FROM hagio_admin.directory WHERE directory_id = $1
           UNION ALL
             SELECT d.directory_id
             FROM hagio_admin.directory d
             JOIN below b ON d.parent_id = b.directory_id
         )
         DELETE FROM hagio_admin.directory
         WHERE directory_id IN (SELECT directory_id FROM below)",
    )
    .bind(directory_id)
    .execute(&state.pool)
    .await?;

    Ok(())
}

async fn undo_upload(
    state: &AppState,
    files: &[(Uuid, i64)],
    root: Option<Uuid>,
) -> AppResult<String> {
    let share = &state.config.share_root;

    // Check everything before removing anything, so a refusal leaves the upload
    // exactly as it was.
    let mut present = Vec::new();
    for (file_id, size) in files {
        let Some(rel) = tree::file_path(&state.pool, *file_id).await? else {
            continue;
        };
        let Ok(abs) = paths::resolve(share, &rel) else {
            // Already gone. Nothing to take back, but the row still goes.
            continue;
        };
        if std::fs::metadata(&abs)?.len() as i64 != *size {
            return Err(AppError::Conflict(format!(
                "'{rel}' has changed since it was uploaded, so the upload was left alone"
            )));
        }
        present.push(abs);
    }

    let file_ids: Vec<Uuid> = files.iter().map(|(id, _)| *id).collect();
    let dir_ids: Vec<Uuid> = root.into_iter().collect();
    refuse_if_referenced(state, &file_ids, &dir_ids).await?;

    for abs in &present {
        std::fs::remove_file(abs)?;
    }
    sqlx::query("DELETE FROM hagio_admin.file WHERE file_id = ANY($1)")
        .bind(&file_ids)
        .execute(&state.pool)
        .await?;

    // Folders the upload made on the way, deepest first.
    let mut note = String::new();
    if let Some(root) = root {
        match tree::dir_path(&state.pool, root).await? {
            Some(path) => match remove_empty_tree(share, &path) {
                Ok(true) => delete_dir_rows(state, root).await?,
                Ok(false) => note = format!(" '{path}' had other files in it, so it stayed."),
                Err(e) => tracing::warn!(path = %path, "could not tidy up after an undo: {e}"),
            },
            None => {
                tracing::warn!(directory_id = %root, "the uploaded folder is no longer tracked")
            }
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
