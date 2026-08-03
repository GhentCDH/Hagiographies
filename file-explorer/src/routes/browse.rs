use axum::{
    Json,
    extract::{Query, State},
};
use serde::{Deserialize, Serialize};

use crate::error::{AppError, AppResult};
use crate::fs_ops;
use crate::models::{Crumb, Entry, Folder, Listing};
use crate::paths::RelPath;
use crate::scan;
use crate::state::AppState;

#[derive(Debug, Deserialize)]
pub struct PathQuery {
    #[serde(default)]
    pub path: String,
}

pub async fn browse(
    State(state): State<AppState>,
    Query(query): Query<PathQuery>,
) -> AppResult<Json<Listing>> {
    let config = &state.config;
    let dir = RelPath::parse(&query.path, &config.excluded_dirs)?;
    let found = fs_ops::list_dir(&config.share_root, &dir, &config.excluded_dirs)?;

    // Listing also adopts files that arrived over SMB, so nobody has to
    // remember to rescan.
    let reconciled = scan::reconcile_dir(&state.pool, &dir, &found).await?;

    let mut entries = Vec::with_capacity(found.len() + reconciled.missing.len());
    for entry in found {
        let path = dir.join(&entry.name, &config.excluded_dirs)?;
        if entry.is_dir {
            // reconcile_dir gave every subfolder here a row, so it has an id to
            // link to.
            let Some(directory_id) = reconciled.subdirs.get(&entry.name).copied() else {
                tracing::warn!(path = %path, "folder vanished mid-listing, omitting it");
                continue;
            };
            entries.push(Entry::Dir {
                name: entry.name,
                path: path.as_str().to_string(),
                directory_id,
                link: config.dir_link_for(directory_id),
            });
            continue;
        }

        // Every file in the listing was just reconciled, so it has an id.
        let Some(file_id) = reconciled.ids.get(&entry.name).copied() else {
            tracing::warn!(path = %path, "file vanished mid-listing, omitting it");
            continue;
        };
        entries.push(Entry::File {
            name: entry.name,
            path: path.as_str().to_string(),
            file_id,
            link: config.link_for(file_id),
            size_bytes: entry.size_bytes,
            modified: entry.modified,
            missing: false,
        });
    }

    // Tracked here but gone from the share. Shown greyed out, because a link to
    // it may already be in the database and otherwise nobody would notice.
    for (name, file_id) in reconciled.missing {
        let path = dir.join(&name, &config.excluded_dirs)?;
        entries.push(Entry::File {
            name,
            path: path.as_str().to_string(),
            file_id,
            link: config.link_for(file_id),
            size_bytes: 0,
            modified: None,
            missing: true,
        });
    }

    Ok(Json(Listing {
        path: dir.as_str().to_string(),
        at_root: dir.is_root(),
        breadcrumbs: breadcrumbs(&dir),
        entries,
    }))
}

fn breadcrumbs(dir: &RelPath) -> Vec<Crumb> {
    let mut crumbs = Vec::new();
    let mut so_far = String::new();
    for segment in dir.segments() {
        if !so_far.is_empty() {
            so_far.push('/');
        }
        so_far.push_str(segment);
        crumbs.push(Crumb {
            name: segment.to_string(),
            path: so_far.clone(),
        });
    }
    crumbs
}

#[derive(Debug, Serialize)]
pub struct FolderList {
    folders: Vec<Folder>,
}

pub async fn folders(State(state): State<AppState>) -> AppResult<Json<FolderList>> {
    let folders = fs_ops::folder_tree(&state.config.share_root, &state.config.excluded_dirs)?;
    Ok(Json(FolderList { folders }))
}

#[derive(Debug, Serialize)]
pub struct RescanReport {
    directories: usize,
    files: usize,
    newly_missing: u64,
}

pub async fn rescan(State(state): State<AppState>) -> AppResult<Json<RescanReport>> {
    let Ok(_guard) = state.scan_lock.try_lock() else {
        return Err(AppError::Conflict("a scan is already running".to_string()));
    };

    let summary = scan::full_scan(
        &state.pool,
        &state.config.share_root,
        &state.config.excluded_dirs,
    )
    .await?;

    tracing::info!(
        directories = summary.directories,
        files = summary.files,
        newly_missing = summary.missing,
        "rescan complete"
    );
    Ok(Json(RescanReport {
        directories: summary.directories,
        files: summary.files,
        newly_missing: summary.missing,
    }))
}
