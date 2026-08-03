use chrono::{DateTime, Utc};
use serde::Serialize;
use uuid::Uuid;

#[derive(Debug, Serialize)]
#[serde(tag = "kind", rename_all = "lowercase")]
pub enum Entry {
    Dir {
        name: String,
        path: String,
        /// Folders are linkable too, at /d/<directory_id>.
        directory_id: Uuid,
        link: String,
    },
    File {
        name: String,
        path: String,
        file_id: Uuid,
        link: String,
        size_bytes: u64,
        modified: Option<DateTime<Utc>>,
        /// The database has a row for it but it is no longer on the share.
        missing: bool,
    },
}

#[derive(Debug, Serialize)]
pub struct Crumb {
    pub name: String,
    pub path: String,
}

#[derive(Debug, Serialize)]
pub struct Listing {
    pub path: String,
    pub at_root: bool,
    pub breadcrumbs: Vec<Crumb>,
    pub entries: Vec<Entry>,
}

/// One destination in the move dialog. Flat with a depth, because the dialog
/// renders it as an indented list.
#[derive(Debug, Serialize)]
pub struct Folder {
    pub path: String,
    pub name: String,
    pub depth: usize,
}
