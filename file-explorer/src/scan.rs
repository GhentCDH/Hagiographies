//! Keeping `hagio_admin.file` and `hagio_admin.directory` in step with the share.
//!
//! The tables have to be a full inventory, not just what this app uploaded: the
//! share already holds files and more arrive over SMB. So [`full_scan`] walks
//! everything at startup and on demand, [`reconcile_dir`] runs on every directory
//! listing, and uploads insert their rows directly.
//!
//! A row is never deleted. Anything that disappears gets `missing_since` set,
//! because a link to its UUID may already be in the database.
//!
//! A file edited directly on the share (moved or renamed over SMB) is not a new
//! file: it has the same bytes. [`reconcile_dir`] hashes every new or changed
//! file (blake3), and [`resolve_candidates`] looks a new file up by its hash
//! among the rows whose file is no longer where the row says it is. That covers
//! both a row already flagged missing by a scan and one still marked present
//! whose recorded path has gone: a browse of the destination must relocate
//! before the source folder has ever been visited. A lone match is relocated in
//! place, keeping its `file_id`, so a `/f/<uuid>` link already pasted into
//! Mathesar keeps working. Only an exact, unambiguous (single) hash match
//! relocates; anything else is a genuinely new row.

use std::collections::HashMap;
use std::path::Path;

use sqlx::PgPool;
use uuid::Uuid;

use crate::error::{AppError, AppResult};
use crate::fs_ops::{self, DirEntryInfo};
use crate::paths::{self, RelPath};
use crate::tree;

#[derive(Debug, Default)]
pub struct Reconciled {
    /// The folder that was reconciled.
    pub directory_id: Uuid,
    /// File name in this folder → its tracked `file_id`, for files that already
    /// had a row here (unchanged or updated in place).
    pub ids: HashMap<String, Uuid>,
    /// Subfolder name → its tracked `directory_id`.
    pub subdirs: HashMap<String, Uuid>,
    /// Tracked here but no longer on the share, by name.
    pub missing: Vec<(String, Uuid)>,
    /// Files on the share here with no row yet. Left unresolved on purpose:
    /// [`resolve_candidates`] decides, once the missing set is known, whether
    /// each is a moved file to relocate or a brand-new one to insert.
    pub candidates: Vec<Candidate>,
}

/// A file present on the share with no `(directory_id, name)` row.
#[derive(Debug, Clone)]
pub struct Candidate {
    pub directory_id: Uuid,
    pub name: String,
    pub size_bytes: i64,
    pub content_type: Option<String>,
    pub hash: Vec<u8>,
}

#[derive(Debug, Default)]
pub struct Resolved {
    /// Name → `file_id` for each candidate, whether relocated or inserted.
    pub ids: Vec<(String, Uuid)>,
    /// How many were a moved/renamed file matched back to its existing row.
    pub relocated: u64,
}

#[derive(Debug, sqlx::FromRow)]
struct TrackedChild {
    file_id: Uuid,
    name: String,
    size_bytes: Option<i64>,
    content_type: Option<String>,
    missing_since: Option<chrono::DateTime<chrono::Utc>>,
    content_hash: Option<Vec<u8>>,
}

/// A row that shares a candidate's bytes, with the path its row still claims.
/// Whether it counts as a match depends on whether that path is still there.
#[derive(Debug, sqlx::FromRow)]
struct HashMatch {
    file_id: Uuid,
    relative_path: String,
    missing_since: Option<chrono::DateTime<chrono::Utc>>,
}

/// Whether a row's file is still at the path the row records.
///
/// A move over SMB leaves the row pointing at the old path until a sweep flags
/// it missing, so the path is simply gone in the meantime. Treating that as a
/// match lets a browse of the destination adopt the row before the source
/// folder has been scanned. A path that will not parse or resolve is gone too.
fn still_present(root: &Path, relative_path: &str) -> bool {
    RelPath::parse(relative_path, &[])
        .and_then(|rel| paths::resolve(root, &rel))
        .is_ok()
}

/// blake3 of the file at `dir`/`name` under `root`, off the async runtime.
async fn hash_at(root: &Path, dir: &RelPath, name: &str) -> AppResult<Vec<u8>> {
    let child = dir.join(name, &[])?;
    let abs = paths::resolve(root, &child)?;
    let hash = tokio::task::spawn_blocking(move || fs_ops::hash_file(&abs))
        .await
        .map_err(|e| std::io::Error::other(format!("hash task failed: {e}")))??;
    Ok(hash.to_vec())
}

/// Bring the rows for one folder in line with what is on the share there.
///
/// New files are hashed and returned as [`Candidate`]s rather than inserted here,
/// so the caller can relocate a moved file instead of minting a new row for it.
pub async fn reconcile_dir(
    pool: &PgPool,
    root: &Path,
    dir: &RelPath,
    entries: &[DirEntryInfo],
) -> AppResult<Reconciled> {
    let directory_id = tree::ensure_dir(pool, dir).await?;

    let tracked = sqlx::query_as::<_, TrackedChild>(
        "SELECT file_id, name, size_bytes, content_type, missing_since, content_hash
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

    // Changed rows that keep their (directory_id, name) are updated in a single
    // upsert per folder; new names become candidates. Unchanged rows are left
    // untouched so browsing does not bump updated_at, and are not rehashed once
    // they carry a hash.
    let mut names = Vec::new();
    let mut sizes = Vec::new();
    let mut types = Vec::new();
    let mut hashes: Vec<Vec<u8>> = Vec::new();

    for entry in entries.iter().filter(|e| !e.is_dir) {
        let size = entry.size_bytes as i64;
        let content_type = fs_ops::guess_content_type(&entry.name);

        if let Some(row) = by_name.get(entry.name.as_str())
            && row.size_bytes == Some(size)
            && row.content_type == content_type
            && row.missing_since.is_none()
            && row.content_hash.is_some()
        {
            result.ids.insert(entry.name.clone(), row.file_id);
            continue;
        }

        let hash = match hash_at(root, dir, &entry.name).await {
            Ok(hash) => hash,
            Err(e) => {
                // A file that cannot be read right now (vanished mid-scan, a
                // permission blip) must not be treated as gone. Keep any existing
                // row as-is and skip; the next scan will pick it up.
                tracing::warn!(dir = %dir, name = %entry.name, "skipping, could not hash: {e}");
                if let Some(row) = by_name.get(entry.name.as_str()) {
                    result.ids.insert(entry.name.clone(), row.file_id);
                }
                continue;
            }
        };

        if by_name.contains_key(entry.name.as_str()) {
            names.push(entry.name.clone());
            sizes.push(size);
            types.push(content_type);
            hashes.push(hash);
        } else {
            result.candidates.push(Candidate {
                directory_id,
                name: entry.name.clone(),
                size_bytes: size,
                content_type,
                hash,
            });
        }
    }

    if !names.is_empty() {
        let upserted = sqlx::query_as::<_, (Uuid, String)>(
            "INSERT INTO hagio_admin.file (directory_id, name, size_bytes, content_type, content_hash)
             SELECT $1, * FROM unnest($2::text[], $3::bigint[], $4::text[], $5::bytea[])
             ON CONFLICT (directory_id, name) DO UPDATE
             SET size_bytes = EXCLUDED.size_bytes,
                 content_type = EXCLUDED.content_type,
                 content_hash = EXCLUDED.content_hash,
                 missing_since = NULL,
                 updated_at = now()
             RETURNING file_id, name",
        )
        .bind(directory_id)
        .bind(&names)
        .bind(&sizes)
        .bind(&types)
        .bind(&hashes)
        .fetch_all(pool)
        .await?;

        for (file_id, name) in upserted {
            result.ids.insert(name, file_id);
        }
    }

    // Anything tracked here that is no longer on the share.
    let present: Vec<&str> = entries
        .iter()
        .filter(|e| !e.is_dir)
        .map(|e| e.name.as_str())
        .collect();
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

/// Give every candidate a `file_id`: relocate the one row whose bytes match and
/// whose file is no longer where that row says it is, or insert a new row when
/// there is no unambiguous match.
///
/// Run this once the missing set is settled (after the sweep in [`full_scan`]),
/// or live in a browse listing. A browse cannot wait for the sweep, so it also
/// treats a still-present row whose recorded path has gone as a match: that is
/// a file moved over SMB whose source folder has not been scanned yet. The match
/// pool is exactly those rows, so a still-present duplicate is never mistaken
/// for the original.
pub async fn resolve_candidates(
    pool: &PgPool,
    root: &Path,
    candidates: &[Candidate],
) -> AppResult<Resolved> {
    let mut out = Resolved::default();

    for cand in candidates {
        let rows = sqlx::query_as::<_, HashMatch>(
            "SELECT f.file_id, p.relative_path, f.missing_since
             FROM hagio_admin.file f
             JOIN hagio_admin.file_path p USING (file_id)
             WHERE f.content_hash = $1",
        )
        .bind(&cand.hash)
        .fetch_all(pool)
        .await?;

        // Two is enough to tell "exactly one" from "ambiguous" without counting.
        let mut matches: Vec<Uuid> = Vec::new();
        for row in rows {
            if row.missing_since.is_some() || !still_present(root, &row.relative_path) {
                matches.push(row.file_id);
                if matches.len() > 1 {
                    break;
                }
            }
        }

        if let [file_id] = matches.as_slice() {
            // A moved or renamed file: repoint its row, same shape as an in-app
            // move, so the file_id and every link through it survive.
            let relocated = sqlx::query(
                "UPDATE hagio_admin.file
                 SET directory_id = $1, name = $2, size_bytes = $3, content_type = $4,
                     content_hash = $5, missing_since = NULL, updated_at = now()
                 WHERE file_id = $6",
            )
            .bind(cand.directory_id)
            .bind(&cand.name)
            .bind(cand.size_bytes)
            .bind(&cand.content_type)
            .bind(&cand.hash)
            .bind(file_id)
            .execute(pool)
            .await;

            match relocated {
                Ok(_) => {
                    out.ids.push((cand.name.clone(), *file_id));
                    out.relocated += 1;
                    continue;
                }
                // A row already sits at this (directory_id, name); fall through and
                // insert, which upserts onto it.
                Err(e)
                    if e.as_database_error().and_then(|e| e.code()).as_deref() == Some("23505") => {
                }
                Err(e) => return Err(AppError::Db(e)),
            }
        }

        let file_id = sqlx::query_scalar::<_, Uuid>(
            "INSERT INTO hagio_admin.file (directory_id, name, size_bytes, content_type, content_hash)
             VALUES ($1, $2, $3, $4, $5)
             ON CONFLICT (directory_id, name) DO UPDATE
             SET size_bytes = EXCLUDED.size_bytes,
                 content_type = EXCLUDED.content_type,
                 content_hash = EXCLUDED.content_hash,
                 missing_since = NULL,
                 updated_at = now()
             RETURNING file_id",
        )
        .bind(cand.directory_id)
        .bind(&cand.name)
        .bind(cand.size_bytes)
        .bind(&cand.content_type)
        .bind(&cand.hash)
        .fetch_one(pool)
        .await?;

        out.ids.push((cand.name.clone(), file_id));
    }

    Ok(out)
}

#[derive(Debug, Default)]
pub struct ScanSummary {
    pub directories: usize,
    pub files: usize,
    pub missing: u64,
    pub relocated: u64,
}

/// Walk the whole share and reconcile every folder.
///
/// Cheap on a second run: [`reconcile_dir`] writes nothing for a file whose size
/// and type are unchanged and already carries a hash.
pub async fn full_scan(pool: &PgPool, root: &Path, excluded: &[String]) -> AppResult<ScanSummary> {
    let mut summary = ScanSummary::default();
    let mut seen_files: Vec<Uuid> = Vec::new();
    let mut seen_dirs: Vec<Uuid> = Vec::new();
    let mut candidates: Vec<Candidate> = Vec::new();

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

        let reconciled = reconcile_dir(pool, root, &dir, &entries).await?;
        summary.directories += 1;
        summary.files += reconciled.ids.len();

        seen_dirs.push(reconciled.directory_id);
        seen_files.extend(reconciled.ids.values().copied());
        candidates.extend(reconciled.candidates);
    }

    // Catches whatever the per-folder pass cannot see: files whose whole folder is
    // gone, and the folders themselves. This also marks things under a folder that
    // was added to excluded_dirs, which is right: they are no longer part of the
    // managed share. Runs before candidates are resolved so a file that moved this
    // scan has its old row marked missing, which is what the match then finds.
    let swept = sqlx::query(
        "UPDATE hagio_admin.file
         SET missing_since = now(), updated_at = now()
         WHERE missing_since IS NULL AND file_id <> ALL($1::uuid[])",
    )
    .bind(&seen_files)
    .execute(pool)
    .await?
    .rows_affected();

    // Relocate the moved/renamed files, insert the rest. A relocation clears the
    // missing_since the sweep just set, so `missing` is the net still-gone count.
    let resolved = resolve_candidates(pool, root, &candidates).await?;
    summary.relocated = resolved.relocated;
    summary.missing = swept.saturating_sub(resolved.relocated);
    summary.files += resolved.ids.len();

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
