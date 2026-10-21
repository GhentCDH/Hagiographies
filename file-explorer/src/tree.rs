//! The one place that converts between a [`RelPath`] and a row id.
//!
//! Everything else in the app works in one currency or the other: the filesystem
//! side speaks paths, the database side speaks `directory_id` and `file_id`. Keep
//! the conversion here and neither has to know how the other spells things.
//!
//! Paths are not stored. They are assembled by the `hagio_admin.directory_path`
//! and `hagio_admin.file_path` views, which walk the tree, so a folder rename is
//! one row and every path below it follows for free.

use sqlx::PgPool;
use uuid::Uuid;

use crate::error::{AppError, AppResult};
use crate::paths::RelPath;

/// The share root, which is the single `directory` row with no parent.
pub async fn root_id(pool: &PgPool) -> AppResult<Uuid> {
    sqlx::query_scalar("SELECT directory_id FROM hagio_admin.directory WHERE parent_id IS NULL")
        .fetch_optional(pool)
        .await?
        .ok_or_else(|| {
            AppError::BadRequest(
                "the share root is missing from the directory table; run the migrations"
                    .to_string(),
            )
        })
}

/// The id of a folder, creating it and any missing folder above it.
///
/// This is also how the scanner records folders it finds on the share, so it has
/// to be an upsert rather than an insert: two listings of the same new folder must
/// not fight.
pub async fn ensure_dir(pool: &PgPool, dir: &RelPath) -> AppResult<Uuid> {
    let mut id = root_id(pool).await?;

    for name in dir.segments() {
        id = sqlx::query_scalar(
            "INSERT INTO hagio_admin.directory (parent_id, name)
             VALUES ($1, $2)
             ON CONFLICT (parent_id, name) DO UPDATE
             SET missing_since = NULL,
                 updated_at = CASE
                     WHEN hagio_admin.directory.missing_since IS NOT NULL THEN now()
                     ELSE hagio_admin.directory.updated_at
                 END
             RETURNING directory_id",
        )
        .bind(id)
        .bind(name)
        .fetch_one(pool)
        .await?;
    }

    Ok(id)
}

/// Where a folder currently sits, or None if that id is not tracked.
pub async fn dir_path(pool: &PgPool, directory_id: Uuid) -> AppResult<Option<RelPath>> {
    let path: Option<String> = sqlx::query_scalar(
        "SELECT relative_path FROM hagio_admin.directory_path WHERE directory_id = $1",
    )
    .bind(directory_id)
    .fetch_optional(pool)
    .await?;

    // `&[]` and not the configured exclusions: this path came out of our own
    // table, and a folder that is excluded now should still resolve so the caller
    // can say so rather than mistaking it for a missing row.
    Ok(match path {
        Some(path) => Some(RelPath::parse(&path, &[])?),
        None => None,
    })
}

/// Where a file currently sits, or None if that id is not tracked.
pub async fn file_path(pool: &PgPool, file_id: Uuid) -> AppResult<Option<RelPath>> {
    let path: Option<String> =
        sqlx::query_scalar("SELECT relative_path FROM hagio_admin.file_path WHERE file_id = $1")
            .bind(file_id)
            .fetch_optional(pool)
            .await?;

    Ok(match path {
        Some(path) => Some(RelPath::parse(&path, &[])?),
        None => None,
    })
}
