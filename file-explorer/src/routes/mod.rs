mod browse;
mod dirs;
mod files;
mod search;
mod serve;
mod undo;

use axum::{
    Json, Router,
    extract::DefaultBodyLimit,
    routing::{get, post},
};
use serde_json::json;
use tower_http::trace::TraceLayer;

use crate::state::AppState;

pub fn build(state: AppState) -> Router {
    let max_upload = state.config.max_upload_bytes;

    let api = Router::new()
        .route("/health", get(health))
        .route("/browse", get(browse::browse))
        .route("/folders", get(browse::folders))
        .route("/search", get(search::search))
        .route("/rescan", post(browse::rescan))
        .route("/undo", get(undo::peek).post(undo::perform))
        .route("/files/{file_id}/rename", post(files::rename))
        .route("/files/{file_id}/move", post(files::move_to))
        .route("/dirs", post(dirs::create))
        .route("/dirs/rename", post(dirs::rename))
        .route("/dirs/move", post(dirs::move_to))
        .route(
            "/upload",
            // Axum's default is 2 MB, which would reject every real scan.
            post(files::upload).layer(DefaultBodyLimit::max(max_upload)),
        )
        .route(
            // The limit is per request, so it caps the whole folder here.
            "/upload-folder",
            post(files::upload_folder).layer(DefaultBodyLimit::max(max_upload)),
        );

    Router::new()
        .nest("/api", api)
        // Outside /api on purpose: this is the public, pasteable URL.
        .route("/f/{file_id}", get(serve::serve))
        .route("/d/{directory_id}", get(serve::serve_dir))
        .layer(TraceLayer::new_for_http())
        .with_state(state)
        .fallback(crate::embed::handler)
}

async fn health() -> Json<serde_json::Value> {
    Json(json!({ "status": "ok" }))
}

/// Reverse a file move. Same code path as the move itself, so the row and the
/// share cannot drift apart.
pub(crate) async fn move_file_back(
    state: &AppState,
    file_id: uuid::Uuid,
    from: &crate::paths::RelPath,
    to: &crate::paths::RelPath,
) -> crate::error::AppResult<()> {
    files::move_file(state, file_id, from, to, "moved back").await
}

/// Reverse a folder move. One row again, so nothing under it is touched.
pub(crate) async fn move_dir_back(
    state: &AppState,
    from: &crate::paths::RelPath,
    to: &crate::paths::RelPath,
) -> crate::error::AppResult<uuid::Uuid> {
    dirs::move_dir(state, from, to, "moved back").await
}
