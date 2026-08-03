//! Keeping `hagio_admin.file` and `hagio_admin.directory` in step with the share.
//!
//! The tables have to be a full inventory, not just what this app uploaded: the
//! share already holds files and more arrive over SMB. So [`full_scan`] walks
//! everything at startup and on demand, [`reconcile_dir`] runs on every directory
//! listing, and uploads insert their rows directly.
//!
//! A row is never deleted. Anything that disappears gets `missing_since` set,
//! because a link to its UUID may already be in the database.

use std::collections::HashMap;
use std::path::Path;

use sqlx::PgPool;
use uuid::Uuid;

use crate::error::AppResult;
use crate::fs_ops::{self, DirEntryInfo};
use crate::paths::RelPath;
use crate::tree;

#[derive(Debug, Default)]
pub struct Reconciled {
    /// The folder that was reconciled.
    pub directory_id: Uuid,
    /// File name in this folder → its tracked `file_id`.
    pub ids: HashMap<String, Uuid>,
    /// Subfolder name → its tracked `directory_id`.
    pub subdirs: HashMap<String, Uuid>,
    /// Tracked here but no longer on the share, by name.
    pub missing: Vec<(String, Uuid)>,
}

#[derive(Debug, sqlx::FromRow)]
struct TrackedChild {
    file_id: Uuid,
    name: String,
    size_bytes: Option<i64>,
    content_type: Option<String>,
    missing_since: Option<chrono::DateTime<chrono::Utc>>,
}

/// Bring the rows for one folder in line with what is on the share there.
pub async fn reconcile_dir(
    pool: &PgPool,
    dir: &RelPath,
    entries: &[DirEntryInfo],
) -> AppResult<Reconciled> {
    let directory_id = tree::ensure_dir(pool, dir).await?;

    let tracked = sqlx::query_as::<_, TrackedChild>(
        "SELECT file_id, name, size_bytes, content_type, missing_since
         FROM hagio_admin.file
         WHERE directory_id = $1",
    )
    .bind(directory_id)
    .fetch_all(pool)
    .await?;

    let by_name: HashMap<&str, &TrackedChild> =
        tracked.iter().map(|row| (row.name.as_str(), row)).collect();

    let mut result = Reconciled {
        directory_id,
        ..Default::default()
    };

    // Subfolders are rows too, so they are tracked as we go and get their own ids
    // for the /d/ links.
    for entry in entries.iter().filter(|e| e.is_dir) {
        let child = dir.join(&entry.name, &[])?;
        let id = tree::ensure_dir(pool, &child).await?;
        result.subdirs.insert(entry.name.clone(), id);
    }

    let files: Vec<&DirEntryInfo> = entries.iter().filter(|e| !e.is_dir).collect();

    // Only touch rows that are new or actually changed, so browsing does not bump
    // updated_at on every file it lists.
    let mut names = Vec::new();
    let mut sizes = Vec::new();
    let mut types = Vec::new();

    for entry in &files {
        let size = entry.size_bytes as i64;
        let content_type = fs_ops::guess_content_type(&entry.name);

        match by_name.get(entry.name.as_str()) {
            Some(row)
                if row.size_bytes == Some(size)
                    && row.content_type == content_type
                    && row.missing_since.is_none() =>
            {
                result.ids.insert(entry.name.clone(), row.file_id);
            }
            _ => {
                names.push(entry.name.clone());
                sizes.push(size);
                types.push(content_type);
            }
        }
    }

    if !names.is_empty() {
        let upserted = sqlx::query_as::<_, (Uuid, String)>(
            "INSERT INTO hagio_admin.file (directory_id, name, size_bytes, content_type)
             SELECT $1, * FROM unnest($2::text[], $3::bigint[], $4::text[])
             ON CONFLICT (directory_id, name) DO UPDATE
             SET size_bytes = EXCLUDED.size_bytes,
                 content_type = EXCLUDED.content_type,
                 missing_since = NULL,
                 updated_at = now()
             RETURNING file_id, name",
        )
        .bind(directory_id)
        .bind(&names)
        .bind(&sizes)
        .bind(&types)
        .fetch_all(pool)
        .await?;

        for (file_id, name) in upserted {
            result.ids.insert(name, file_id);
        }
    }

    // Anything tracked here that is no longer on the share.
    let present: Vec<&str> = files.iter().map(|e| e.name.as_str()).collect();
    for row in &tracked {
        if !present.contains(&row.name.as_str()) {
            result.missing.push((row.name.clone(), row.file_id));
        }
    }
    result.missing.sort_by_key(|(name, _)| name.to_lowercase());

    if !result.missing.is_empty() {
        let ids: Vec<Uuid> = result.missing.iter().map(|(_, id)| *id).collect();
        sqlx::query(
            "UPDATE hagio_admin.file
             SET missing_since = now(), updated_at = now()
             WHERE file_id = ANY($1) AND missing_since IS NULL",
        )
        .bind(&ids)
        .execute(pool)
        .await?;
    }

    Ok(result)
}

#[derive(Debug, Default)]
pub struct ScanSummary {
    pub directories: usize,
    pub files: usize,
    pub missing: u64,
}

/// Walk the whole share and reconcile every folder.
///
/// Cheap on a second run: [`reconcile_dir`] writes nothing for a file whose size
/// and type are unchanged.
pub async fn full_scan(pool: &PgPool, root: &Path, excluded: &[String]) -> AppResult<ScanSummary> {
    let mut summary = ScanSummary::default();
    let mut seen_files: Vec<Uuid> = Vec::new();
    let mut seen_dirs: Vec<Uuid> = Vec::new();

    for dir in fs_ops::all_directories(root, excluded) {
        // A folder can disappear between the walk and the read; that is not an
        // error, the sweep below marks its contents missing.
        let entries = match fs_ops::list_dir(root, &dir, excluded) {
            Ok(entries) => entries,
            Err(e) => {
                tracing::warn!(dir = %dir, "skipping directory during scan: {e}");
                continue;
            }
        };

        let reconciled = reconcile_dir(pool, &dir, &entries).await?;
        summary.directories += 1;
        summary.files += reconciled.ids.len();

        seen_dirs.push(reconciled.directory_id);
        seen_files.extend(reconciled.ids.values().copied());
    }

    // Catches whatever the per-folder pass cannot see: files whose whole folder is
    // gone, and the folders themselves. This also marks things under a folder that
    // was added to excluded_dirs, which is right: they are no longer part of the
    // managed share.
    summary.missing = sqlx::query(
        "UPDATE hagio_admin.file
         SET missing_since = now(), updated_at = now()
         WHERE missing_since IS NULL AND file_id <> ALL($1::uuid[])",
    )
    .bind(&seen_files)
    .execute(pool)
    .await?
    .rows_affected();

    sqlx::query(
        "UPDATE hagio_admin.directory
         SET missing_since = now(), updated_at = now()
         WHERE missing_since IS NULL
           AND parent_id IS NOT NULL
           AND directory_id <> ALL($1::uuid[])",
    )
    .bind(&seen_dirs)
    .execute(pool)
    .await?;

    Ok(summary)
}
