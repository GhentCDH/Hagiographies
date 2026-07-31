//! Keeping `hagio_admin.file` in step with what is actually on the share.
//!
//! The table has to be a full inventory, not just what this app uploaded: the
//! share already holds files and more arrive over SMB. So [`full_scan`] walks
//! everything at startup and on demand, [`reconcile_dir`] runs on every
//! directory listing, and uploads insert their row directly.
//!
//! A row is never deleted. A file that disappears gets `missing_since` set,
//! because a link to its UUID may already be in the database.

use std::collections::HashMap;
use std::path::Path;

use sqlx::PgPool;
use uuid::Uuid;

use crate::error::AppResult;
use crate::fs_ops::{self, DirEntryInfo};
use crate::paths::RelPath;

#[derive(Debug, Default)]
pub struct Reconciled {
    /// File name in this directory → its tracked `file_id`.
    pub ids: HashMap<String, Uuid>,
    /// Tracked here but no longer on the share, newest first by name.
    pub missing: Vec<(String, Uuid)>,
}

#[derive(Debug, sqlx::FromRow)]
struct TrackedChild {
    file_id: Uuid,
    relative_path: String,
    size_bytes: Option<i64>,
    content_type: Option<String>,
    missing_since: Option<chrono::DateTime<chrono::Utc>>,
}

/// Escape a string for use as a literal prefix in `LIKE ... ESCAPE '\'`.
pub fn like_prefix(prefix: &str) -> String {
    let mut out = String::with_capacity(prefix.len() + 2);
    for ch in prefix.chars() {
        if matches!(ch, '\\' | '%' | '_') {
            out.push('\\');
        }
        out.push(ch);
    }
    out.push('%');
    out
}

/// Rows tracked as direct children of `dir`.
async fn tracked_children(pool: &PgPool, dir: &RelPath) -> AppResult<Vec<TrackedChild>> {
    let prefix = if dir.is_root() {
        String::new()
    } else {
        format!("{dir}/")
    };

    // strpos on the part after the prefix is what makes this direct children
    // rather than everything below. The LIKE prefix uses the index.
    let rows = sqlx::query_as::<_, TrackedChild>(
        "SELECT file_id, relative_path, size_bytes, content_type, missing_since
         FROM hagio_admin.file
         WHERE relative_path LIKE $1 ESCAPE '\\'
           AND strpos(substr(relative_path, $2), '/') = 0",
    )
    .bind(like_prefix(&prefix))
    .bind(prefix.len() as i32 + 1)
    .fetch_all(pool)
    .await?;

    Ok(rows)
}

/// Bring the `file` rows for one directory in line with the entries found there.
pub async fn reconcile_dir(
    pool: &PgPool,
    dir: &RelPath,
    entries: &[DirEntryInfo],
) -> AppResult<Reconciled> {
    let tracked = tracked_children(pool, dir).await?;
    let by_name: HashMap<&str, &TrackedChild> = tracked
        .iter()
        .filter_map(|row| row.relative_path.rsplit('/').next().map(|name| (name, row)))
        .collect();

    let files: Vec<&DirEntryInfo> = entries.iter().filter(|e| !e.is_dir).collect();

    let mut result = Reconciled::default();

    // Only touch rows that are new or actually changed, so browsing does not
    // bump updated_at on every file it lists.
    let mut paths = Vec::new();
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
                let rel = if dir.is_root() {
                    entry.name.clone()
                } else {
                    format!("{dir}/{}", entry.name)
                };
                paths.push(rel);
                sizes.push(size);
                types.push(content_type);
            }
        }
    }

    if !paths.is_empty() {
        let upserted = sqlx::query_as::<_, (Uuid, String)>(
            "INSERT INTO hagio_admin.file (relative_path, size_bytes, content_type)
             SELECT * FROM unnest($1::text[], $2::bigint[], $3::text[])
             ON CONFLICT (relative_path) DO UPDATE
             SET size_bytes = EXCLUDED.size_bytes,
                 content_type = EXCLUDED.content_type,
                 missing_since = NULL,
                 updated_at = now()
             RETURNING file_id, relative_path",
        )
        .bind(&paths)
        .bind(&sizes)
        .bind(&types)
        .fetch_all(pool)
        .await?;

        for (file_id, relative_path) in upserted {
            if let Some(name) = relative_path.rsplit('/').next() {
                result.ids.insert(name.to_string(), file_id);
            }
        }
    }

    // Anything tracked here that is no longer on the share.
    let present: Vec<&str> = files.iter().map(|e| e.name.as_str()).collect();
    for row in &tracked {
        let Some(name) = row.relative_path.rsplit('/').next() else {
            continue;
        };
        if !present.contains(&name) {
            result.missing.push((name.to_string(), row.file_id));
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

/// Walk the whole share and reconcile every directory.
///
/// Cheap on a second run: [`reconcile_dir`] writes nothing for a file whose size
/// and type are unchanged.
pub async fn full_scan(pool: &PgPool, root: &Path, excluded: &[String]) -> AppResult<ScanSummary> {
    let mut summary = ScanSummary::default();
    let mut seen: Vec<String> = Vec::new();

    for dir in fs_ops::all_directories(root, excluded) {
        // A directory can disappear between the walk and the read; that is not
        // an error, the sweep below will mark its files missing.
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

        for name in reconciled.ids.keys() {
            seen.push(if dir.is_root() {
                name.clone()
            } else {
                format!("{dir}/{name}")
            });
        }
    }

    // Catches files whose whole directory is gone, which the per-directory pass
    // cannot see. This also marks files under a directory that was added to
    // excluded_dirs, which is right: they are no longer part of the share.
    summary.missing = sqlx::query(
        "UPDATE hagio_admin.file
         SET missing_since = now(), updated_at = now()
         WHERE missing_since IS NULL AND relative_path <> ALL($1::text[])",
    )
    .bind(&seen)
    .execute(pool)
    .await?
    .rows_affected();

    Ok(summary)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn like_prefix_escapes_wildcards() {
        assert_eq!(like_prefix(""), "%");
        assert_eq!(like_prefix("scans/"), "scans/%");
        assert_eq!(like_prefix("100%_raw/"), r"100\%\_raw/%");
        assert_eq!(like_prefix(r"a\b/"), r"a\\b/%");
    }
}
