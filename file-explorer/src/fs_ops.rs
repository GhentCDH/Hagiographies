//! Filesystem side of the explorer. Knows nothing about the database.
//!
//! Symlinks are skipped rather than shown. A link's target may be outside the
//! share, and listing something that cannot be opened, renamed or moved is
//! worse than not listing it at all.

use std::fs;
use std::path::{Path, PathBuf};

use chrono::{DateTime, Utc};

use crate::error::{AppError, AppResult};
use crate::models::Folder;
use crate::paths::{self, RelPath};

/// How deep the move dialog's folder list goes.
const FOLDER_TREE_MAX_DEPTH: usize = 12;

#[derive(Debug)]
pub struct DirEntryInfo {
    pub name: String,
    pub is_dir: bool,
    pub size_bytes: u64,
    pub modified: Option<DateTime<Utc>>,
}

/// Direct children of `dir`. Skips hidden entries and symlinks, and at the
/// root also skips the excluded directories.
pub fn list_dir(root: &Path, dir: &RelPath, excluded: &[String]) -> AppResult<Vec<DirEntryInfo>> {
    let abs = paths::resolve(root, dir)?;
    if !abs.is_dir() {
        return Err(AppError::BadRequest(format!("'{dir}' is not a directory")));
    }

    let mut out = Vec::new();
    for entry in fs::read_dir(&abs)? {
        let entry = entry?;
        // A name that is not UTF-8 cannot go into JSON or a text column.
        let Some(name) = entry.file_name().to_str().map(str::to_string) else {
            continue;
        };
        if paths::is_hidden_entry(&name) {
            continue;
        }

        let file_type = entry.file_type()?;
        if file_type.is_symlink() {
            continue;
        }
        if dir.is_root() && excluded.contains(&name) {
            continue;
        }

        let metadata = entry.metadata()?;
        out.push(DirEntryInfo {
            name,
            is_dir: file_type.is_dir(),
            size_bytes: metadata.len(),
            modified: metadata.modified().ok().map(DateTime::<Utc>::from),
        });
    }

    // Directories first, then files, both case-insensitively by name.
    out.sort_by(|a, b| {
        b.is_dir
            .cmp(&a.is_dir)
            .then_with(|| a.name.to_lowercase().cmp(&b.name.to_lowercase()))
    });
    Ok(out)
}

/// Every directory on the share, flattened with a depth for indentation.
pub fn folder_tree(root: &Path, excluded: &[String]) -> AppResult<Vec<Folder>> {
    let mut out = vec![Folder {
        path: String::new(),
        name: "share root".to_string(),
        depth: 0,
    }];
    collect_folders(root, &RelPath::root(), excluded, &mut out)?;
    Ok(out)
}

fn collect_folders(
    root: &Path,
    dir: &RelPath,
    excluded: &[String],
    out: &mut Vec<Folder>,
) -> AppResult<()> {
    if dir.depth() >= FOLDER_TREE_MAX_DEPTH {
        return Ok(());
    }
    for entry in list_dir(root, dir, excluded)? {
        if !entry.is_dir {
            continue;
        }
        let child = dir.join(&entry.name, excluded)?;
        out.push(Folder {
            path: child.as_str().to_string(),
            name: entry.name,
            depth: child.depth(),
        });
        collect_folders(root, &child, excluded, out)?;
    }
    Ok(())
}

/// Every directory under the share root, deepest-last, for the full scan.
pub fn all_directories(root: &Path, excluded: &[String]) -> Vec<RelPath> {
    let mut out = vec![RelPath::root()];
    let walker = walkdir::WalkDir::new(root)
        .follow_links(false)
        .min_depth(1)
        .into_iter()
        .filter_entry(|entry| {
            let name = entry.file_name().to_string_lossy();
            if paths::is_hidden_entry(&name) {
                return false;
            }
            // `excluded` names top-level directories only.
            if entry.depth() == 1 && excluded.iter().any(|e| *e == name) {
                return false;
            }
            true
        });

    for entry in walker.filter_map(Result::ok) {
        if !entry.file_type().is_dir() {
            continue;
        }
        if let Some(rel) = paths::relativise(root, entry.path()) {
            out.push(rel);
        }
    }
    out
}

/// Move `from` to `to`, refusing to overwrite. Both are absolute and already
/// proven to be inside the share.
pub fn rename(from: &Path, to: &Path) -> AppResult<()> {
    // fs::rename overwrites silently, and a clobbered file is not recoverable.
    if to.symlink_metadata().is_ok() {
        return Err(AppError::Conflict(format!(
            "'{}' already exists here",
            to.file_name().unwrap_or_default().to_string_lossy()
        )));
    }
    fs::rename(from, to)?;
    Ok(())
}

pub fn create_dir(at: &Path) -> AppResult<()> {
    if at.symlink_metadata().is_ok() {
        return Err(AppError::Conflict(format!(
            "'{}' already exists here",
            at.file_name().unwrap_or_default().to_string_lossy()
        )));
    }
    fs::create_dir(at)?;
    Ok(())
}

/// Temp path for an upload, in the destination directory so the final rename
/// stays on one filesystem and is atomic.
pub fn temp_path_beside(target: &Path) -> PathBuf {
    let name = target.file_name().unwrap_or_default().to_string_lossy();
    target.with_file_name(format!(".upload-{}-{}", uuid::Uuid::new_v4(), name))
}

pub fn guess_content_type(name: &str) -> Option<String> {
    mime_guess::from_path(name)
        .first()
        .map(|mime| mime.to_string())
}
