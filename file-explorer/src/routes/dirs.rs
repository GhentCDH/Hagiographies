use axum::{Json, extract::State};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

use crate::error::{AppError, AppResult};
use crate::fs_ops;
use crate::paths::{self, RelPath};
use crate::state::AppState;
use crate::tree;
use crate::undo::{Step, Who};

#[derive(Debug, Serialize)]
pub struct DirResponse {
    directory_id: Uuid,
    path: String,
    name: String,
    link: String,
}

impl DirResponse {
    fn new(state: &AppState, directory_id: Uuid, path: &RelPath) -> Self {
        DirResponse {
            directory_id,
            path: path.as_str().to_string(),
            name: path.file_name().unwrap_or_default().to_string(),
            link: state.config.dir_link_for(directory_id),
        }
    }
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
    let directory_id = tree::ensure_dir(&state.pool, &target).await?;

    tracing::info!(path = %target, directory_id = %directory_id, "directory created");
    state
        .undo
        .push(
            &who,
            format!("creating the folder '{target}'"),
            Step::DirCreated { directory_id },
        )
        .await;

    Ok(Json(DirResponse::new(&state, directory_id, &target)))
}

#[derive(Debug, Deserialize)]
pub struct RenameBody {
    pub path: String,
    pub name: String,
}

/// Rename a folder at any level, including the top one.
///
/// One row changes. Nothing below it moves, and no id changes, so nothing already
/// pasted into Mathesar breaks: that is the whole reason links carry a UUID.
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
    let old_name = current.file_name().unwrap_or_default().to_string();

    let directory_id = relocate(&state, &current, &target, "renamed").await?;
    if target != current {
        state
            .undo
            .push(
                &who,
                format!("renaming the folder '{current}' to '{target}'"),
                Step::DirRenamed {
                    directory_id,
                    old_name,
                },
            )
            .await;
    }

    Ok(Json(DirResponse::new(&state, directory_id, &target)))
}

#[derive(Debug, Deserialize)]
pub struct MoveBody {
    pub path: String,
    pub dest_dir: String,
}

/// Move a folder into another one, with everything under it.
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
    // The top level layout of the share is fixed. Moving a top level folder into a
    // subfolder would remove one, which is the same thing creating one is not
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

    let old_parent_id = match current.parent() {
        Some(parent) => tree::ensure_dir(&state.pool, &parent).await?,
        None => tree::root_id(&state.pool).await?,
    };

    let directory_id = relocate(&state, &current, &target, "moved").await?;
    if target != current {
        state
            .undo
            .push(
                &who,
                format!("moving the folder '{current}' to '{dest_dir}'"),
                Step::DirMoved {
                    directory_id,
                    old_parent_id,
                },
            )
            .await;
    }

    Ok(Json(DirResponse::new(&state, directory_id, &target)))
}

/// Move the folder on the share and repoint its row. Returns its id, which does
/// not change.
async fn relocate(
    state: &AppState,
    current: &RelPath,
    target: &RelPath,
    verb: &'static str,
) -> AppResult<Uuid> {
    if target == current {
        return tree::ensure_dir(&state.pool, current).await;
    }
    move_dir(state, current, target, verb).await
}

/// Move a folder: rename it on the share, then repoint the one row that says where
/// it is. Everything below follows for free, because paths are derived from the
/// tree rather than stored.
pub(crate) async fn move_dir(
    state: &AppState,
    current: &RelPath,
    target: &RelPath,
    verb: &'static str,
) -> AppResult<Uuid> {
    let root = &state.config.share_root;
    let from = paths::resolve(root, current)?;
    if !from.is_dir() {
        return Err(AppError::BadRequest(format!(
            "'{current}' is not a directory"
        )));
    }
    let to = paths::resolve_new(root, target)?;

    let directory_id = tree::ensure_dir(&state.pool, current).await?;
    let new_parent_id = match target.parent() {
        Some(parent) => tree::ensure_dir(&state.pool, &parent).await?,
        None => tree::root_id(&state.pool).await?,
    };

    fs_ops::rename(&from, &to)?;

    let written = sqlx::query(
        "UPDATE hagio_admin.directory
         SET parent_id = $1, name = $2, missing_since = NULL, updated_at = now()
         WHERE directory_id = $3",
    )
    .bind(new_parent_id)
    .bind(target.file_name().unwrap_or_default())
    .bind(directory_id)
    .execute(&state.pool)
    .await;

    if let Err(error) = written {
        // A disagreement here would misdirect every link under this folder.
        if let Err(undo) = std::fs::rename(&to, &from) {
            tracing::error!(
                from = %from.display(), to = %to.display(),
                "could not undo a directory {verb} after the database write failed: {undo}"
            );
        }
        if error.as_database_error().and_then(|e| e.code()).as_deref() == Some("23505") {
            return Err(AppError::Conflict(format!(
                "another tracked folder already claims '{target}'; rescan the share and try again"
            )));
        }
        return Err(error.into());
    }

    tracing::info!(from = %current, to = %target, directory_id = %directory_id, "directory {verb}");
    Ok(directory_id)
}
