use axum::{
    extract::{Path, Query, Request, State},
    http::{HeaderValue, header},
    response::Response,
};
use serde::Deserialize;
use tower::ServiceExt;
use tower_http::services::ServeFile;
use uuid::Uuid;

use crate::error::{AppError, AppResult};
use crate::models::FileRow;
use crate::paths::{self, RelPath};
use crate::state::AppState;

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

    let row = sqlx::query_as::<_, FileRow>(
        "SELECT relative_path FROM hagio_admin.file WHERE file_id = $1",
    )
    .bind(file_id)
    .fetch_optional(&state.pool)
    .await?
    .ok_or_else(|| AppError::NotFound("this link does not point at a known file".to_string()))?;

    let rel = RelPath::parse(&row.relative_path, &config.excluded_dirs)?;
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn quotes_and_non_ascii_names_are_safe_in_the_header() {
        let header = content_disposition("inline", "Köln \"6\".pdf");
        assert!(header.starts_with("inline; filename=\"K_ln _6_.pdf\""));
        assert!(header.contains("filename*=UTF-8''K%C3%B6ln%20%226%22.pdf"));
    }
}
