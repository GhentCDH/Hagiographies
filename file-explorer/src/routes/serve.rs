use axum::{
    extract::{Path, Query, Request, State},
    http::{HeaderValue, header},
    response::{IntoResponse, Redirect, Response},
};
use serde::Deserialize;
use tower::ServiceExt;
use tower_http::services::ServeFile;
use uuid::Uuid;

use crate::error::{AppError, AppResult};
use crate::paths;
use crate::state::AppState;
use crate::tree;

#[derive(Debug, Deserialize)]
pub struct ServeQuery {
    /// Any value means "save it" instead of "show it in the browser".
    pub download: Option<String>,
}

/// The public URL students paste into Mathesar.
pub async fn serve(
    State(state): State<AppState>,
    Path(file_id): Path<Uuid>,
    Query(query): Query<ServeQuery>,
    request: Request,
) -> AppResult<Response> {
    let config = &state.config;

    let rel = tree::file_path(&state.pool, file_id)
        .await?
        .ok_or_else(|| {
            AppError::NotFound("this link does not point at a known file".to_string())
        })?;

    let abs = match paths::resolve(&config.share_root, &rel) {
        Ok(abs) => abs,
        Err(e) => {
            mark_missing(&state, file_id).await;
            tracing::warn!(file_id = %file_id, path = %rel, "link points at a file that is gone: {e}");
            return Err(AppError::NotFound(
                "the file this link points at is no longer on the share".to_string(),
            ));
        }
    };

    // ServeFile rather than reading the file ourselves, so range requests, ETag
    // and Last-Modified all work. Researchers page through 300 MB PDFs in the
    // browser and that needs ranges.
    let mut response = match ServeFile::new(&abs).oneshot(request).await {
        Ok(response) => response.map(axum::body::Body::new),
        Err(never) => match never {},
    };

    let name = rel.file_name().unwrap_or("file");
    let disposition = if query.download.is_some() {
        "attachment"
    } else {
        "inline"
    };

    // Every opening is logged. These links get pasted into the database and mailed
    // around, so knowing which files are actually being fetched, and how often, is
    // the only way to answer that later.
    tracing::info!(
        file_id = %file_id,
        path = %rel,
        disposition,
        status = response.status().as_u16(),
        "file opened"
    );
    if let Ok(value) = HeaderValue::from_str(&content_disposition(disposition, name)) {
        response
            .headers_mut()
            .insert(header::CONTENT_DISPOSITION, value);
    }

    Ok(response)
}

async fn mark_missing(state: &AppState, file_id: Uuid) {
    let result = sqlx::query(
        "UPDATE hagio_admin.file
         SET missing_since = now(), updated_at = now()
         WHERE file_id = $1 AND missing_since IS NULL",
    )
    .bind(file_id)
    .execute(&state.pool)
    .await;

    if let Err(e) = result {
        tracing::error!(file_id = %file_id, "could not record the file as missing: {e}");
    }
}

/// Both filename forms from RFC 6266: a plain ASCII one for old clients and a
/// UTF-8 one with the real name.
fn content_disposition(disposition: &str, name: &str) -> String {
    let ascii: String = name
        .chars()
        .map(|c| {
            if c.is_ascii() && c != '"' && c != '\\' && !c.is_control() {
                c
            } else {
                '_'
            }
        })
        .collect();

    format!(
        "{disposition}; filename=\"{ascii}\"; filename*=UTF-8''{}",
        percent_encode(name)
    )
}

fn percent_encode(value: &str) -> String {
    let mut out = String::with_capacity(value.len());
    for byte in value.as_bytes() {
        if byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'.' | b'_' | b'~') {
            out.push(*byte as char);
        } else {
            out.push_str(&format!("%{byte:02X}"));
        }
    }
    out
}

/// The public URL for a folder. Answers a redirect into the explorer rather than
/// any content of its own: a link to a place should take you to the place, and the
/// explorer already knows how to show one.
pub async fn serve_dir(
    State(state): State<AppState>,
    Path(directory_id): Path<Uuid>,
) -> AppResult<Response> {
    let config = &state.config;

    let rel = tree::dir_path(&state.pool, directory_id)
        .await?
        .ok_or_else(|| {
            AppError::NotFound("this link does not point at a known folder".to_string())
        })?;

    // A folder that is gone gets the same treatment as a missing file: recorded,
    // then reported.
    if paths::resolve(&config.share_root, &rel).is_err() {
        let result = sqlx::query(
            "UPDATE hagio_admin.directory
             SET missing_since = now(), updated_at = now()
             WHERE directory_id = $1 AND missing_since IS NULL",
        )
        .bind(directory_id)
        .execute(&state.pool)
        .await;
        if let Err(e) = result {
            tracing::error!(directory_id = %directory_id, "could not record the folder as missing: {e}");
        }
        tracing::warn!(directory_id = %directory_id, path = %rel, "link points at a folder that is gone");
        return Err(AppError::NotFound(
            "the folder this link points at is no longer on the share".to_string(),
        ));
    }

    // The explorer keeps the current folder in the fragment, so this is a link
    // into the single page app rather than another route.
    let target = if rel.is_root() {
        format!("{}/#/", config.public_base_url)
    } else {
        format!("{}/#/{}", config.public_base_url, encode_path(rel.as_str()))
    };

    tracing::info!(directory_id = %directory_id, path = %rel, "folder opened");

    Ok(Redirect::to(&target).into_response())
}

/// Percent-encode the parts of a path that cannot travel in a URL, leaving the
/// separators alone so the fragment still reads as a path.
fn encode_path(path: &str) -> String {
    path.split('/')
        .map(percent_encode)
        .collect::<Vec<_>>()
        .join("/")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_path_is_encoded_without_losing_its_separators() {
        assert_eq!(encode_path("scans/koln 6"), "scans/koln%206");
        assert_eq!(encode_path("Köln"), "K%C3%B6ln");
        // The separators have to survive, or the fragment stops being a path.
        assert_eq!(encode_path("a/b/c"), "a/b/c");
    }

    #[test]
    fn quotes_and_non_ascii_names_are_safe_in_the_header() {
        let header = content_disposition("inline", "Köln \"6\".pdf");
        assert!(header.starts_with("inline; filename=\"K_ln _6_.pdf\""));
        assert!(header.contains("filename*=UTF-8''K%C3%B6ln%20%226%22.pdf"));
    }
}
