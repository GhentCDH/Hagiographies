use axum::{Json, extract::State};
use serde::{Deserialize, Serialize};

use crate::error::{AppError, AppResult};
use crate::fs_ops;
use crate::paths::{self, RelPath};
use crate::scan;
use crate::state::AppState;
use crate::undo::{Step, Who};

#[derive(Debug, Serialize)]
pub struct DirResponse {
    path: String,
    name: String,
    /// How many tracked files had their recorded path rewritten.
    files_updated: u64,
}

#[derive(Debug, Deserialize)]
pub struct CreateBody {
    pub parent: String,
    pub name: String,
}

pub async fn create(
    State(state): State<AppState>,
    who: Who,
    Json(body): Json<CreateBody>,
) -> AppResult<Json<DirResponse>> {
    let config = &state.config;
    let parent = RelPath::parse(&body.parent, &config.excluded_dirs)?;

    // The top level of the share is the one part students do not get to change.
    if parent.is_root() {
        return Err(AppError::BadRequest(
            "new folders can only be made inside an existing folder, not at the top level of the share"
                .to_string(),
        ));
    }

    let target = parent.join_new(body.name.trim(), &config.excluded_dirs)?;
    fs_ops::create_dir(&paths::resolve_new(&config.share_root, &target)?)?;

    tracing::info!(path = %target, "directory created");
    state
        .undo
        .push(
            &who,
            format!("creating the folder '{target}'"),
            Step::DirCreated {
                path: target.clone(),
            },
        )
        .await;
    Ok(Json(DirResponse {
        path: target.as_str().to_string(),
        name: target.file_name().unwrap_or_default().to_string(),
        files_updated: 0,
    }))
}

#[derive(Debug, Deserialize)]
pub struct RenameBody {
    pub path: String,
    pub name: String,
}

/// Rename a directory at any level, including the top one.
///
/// No file_id changes, so nothing already pasted into Mathesar breaks. That is
/// the reason links carry a UUID instead of a path.
pub async fn rename(
    State(state): State<AppState>,
    who: Who,
    Json(body): Json<RenameBody>,
) -> AppResult<Json<DirResponse>> {
    let excluded = &state.config.excluded_dirs;

    let current = RelPath::parse(&body.path, excluded)?;
    if current.is_root() {
        return Err(AppError::BadRequest(
            "the share root itself cannot be renamed".to_string(),
        ));
    }

    let target = current.with_file_name(body.name.trim(), excluded)?;
    relocate(&state, &who, &current, &target, "renamed").await
}

#[derive(Debug, Deserialize)]
pub struct MoveBody {
    pub path: String,
    pub dest_dir: String,
}

/// Move a directory into another one, with everything inside it.
pub async fn move_to(
    State(state): State<AppState>,
    who: Who,
    Json(body): Json<MoveBody>,
) -> AppResult<Json<DirResponse>> {
    let config = &state.config;
    let excluded = &config.excluded_dirs;

    let current = RelPath::parse(&body.path, excluded)?;
    if current.is_root() {
        return Err(AppError::BadRequest(
            "the share root itself cannot be moved".to_string(),
        ));
    }
    // The top level layout of the share is fixed. Moving a top level folder into
    // a subfolder would remove one, which is the same thing creating one is not
    // allowed to do. Renaming it is still fine.
    if current.depth() == 1 {
        return Err(AppError::BadRequest(format!(
            "'{current}' is a top level folder, so it can be renamed but not moved"
        )));
    }

    let dest_dir = RelPath::parse(&body.dest_dir, excluded)?;
    // ...and for the same reason, nothing may be moved up to the top level.
    if dest_dir.is_root() {
        return Err(AppError::BadRequest(
            "a folder cannot be moved to the top level of the share".to_string(),
        ));
    }
    // Without this the rename below fails with a bare EINVAL from the kernel.
    if dest_dir.starts_with(&current) {
        return Err(AppError::BadRequest(format!(
            "'{current}' cannot be moved into itself"
        )));
    }
    if !paths::resolve(&config.share_root, &dest_dir)?.is_dir() {
        return Err(AppError::BadRequest(format!(
            "'{dest_dir}' is not a directory"
        )));
    }

    let name = current
        .file_name()
        .ok_or_else(|| AppError::BadRequest("that folder has no name to move".to_string()))?;
    let target = dest_dir.join(name, excluded)?;

    relocate(&state, &who, &current, &target, "moved").await
}

/// Move the directory and answer with what changed.
async fn relocate(
    state: &AppState,
    who: &Who,
    current: &RelPath,
    target: &RelPath,
    verb: &'static str,
) -> AppResult<Json<DirResponse>> {
    let describe = |files_updated| {
        Json(DirResponse {
            path: target.as_str().to_string(),
            name: target.file_name().unwrap_or_default().to_string(),
            files_updated,
        })
    };
    if target == current {
        return Ok(describe(0));
    }

    let files_updated = move_dir(state, current, target, verb).await?;
    state
        .undo
        .push(
            who,
            format!("{verb} the folder '{current}' to '{target}'"),
            Step::DirMoved {
                from: current.clone(),
                to: target.clone(),
            },
        )
        .await;
    Ok(describe(files_updated))
}

/// Move the directory, then re-prefix the recorded path of everything under it.
/// Returns how many rows were rewritten.
pub(crate) async fn move_dir(
    state: &AppState,
    current: &RelPath,
    target: &RelPath,
    verb: &'static str,
) -> AppResult<u64> {
    let root = &state.config.share_root;
    let from = paths::resolve(root, current)?;
    if !from.is_dir() {
        return Err(AppError::BadRequest(format!(
            "'{current}' is not a directory"
        )));
    }
    let to = paths::resolve_new(root, target)?;

    fs_ops::rename(&from, &to)?;

    match rewrite_paths(state, current, target).await {
        Ok(files_updated) => {
            tracing::info!(from = %current, to = %target, files_updated, "directory {verb}");
            Ok(files_updated)
        }
        Err(error) => {
            // A disagreement here would break every link under this directory.
            if let Err(undo) = std::fs::rename(&to, &from) {
                tracing::error!(
                    from = %from.display(), to = %to.display(),
                    "could not undo a directory {verb} after the database write failed: {undo}"
                );
            }
            Err(error)
        }
    }
}

/// Re-prefix every tracked path under `current` in one statement.
async fn rewrite_paths(state: &AppState, current: &RelPath, target: &RelPath) -> AppResult<u64> {
    let old_prefix = format!("{current}/");
    let new_prefix = format!("{target}/");

    let updated = sqlx::query(
        "UPDATE hagio_admin.file
         SET relative_path = $1 || substr(relative_path, $2), updated_at = now()
         WHERE relative_path LIKE $3 ESCAPE '\\'",
    )
    .bind(&new_prefix)
    .bind(old_prefix.len() as i32 + 1)
    .bind(scan::like_prefix(&old_prefix))
    .execute(&state.pool)
    .await
    .map_err(|error| {
        if error.as_database_error().and_then(|e| e.code()).as_deref() == Some("23505") {
            AppError::Conflict(format!(
                "some tracked paths under '{target}' already exist; rescan the share and try again"
            ))
        } else {
            AppError::Db(error)
        }
    })?
    .rows_affected();

    Ok(updated)
}
