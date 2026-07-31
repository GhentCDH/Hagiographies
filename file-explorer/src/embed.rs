//! The Svelte build, compiled into the binary so deployment is one file.

use axum::{
    body::Body,
    http::{HeaderValue, StatusCode, Uri, header},
    response::{IntoResponse, Response},
};
use rust_embed::RustEmbed;

#[derive(RustEmbed)]
#[folder = "frontend/dist/"]
struct Assets;

pub async fn handler(uri: Uri) -> Response {
    let path = uri.path().trim_start_matches('/');
    serve(if path.is_empty() { "index.html" } else { path })
}

fn serve(path: &str) -> Response {
    match Assets::get(path) {
        Some(asset) => {
            let mime = mime_guess::from_path(path).first_or_octet_stream();
            Response::builder()
                .status(StatusCode::OK)
                .header(
                    header::CONTENT_TYPE,
                    HeaderValue::from_str(mime.as_ref())
                        .unwrap_or_else(|_| HeaderValue::from_static("application/octet-stream")),
                )
                .body(Body::from(asset.data))
                .unwrap_or_else(|_| StatusCode::INTERNAL_SERVER_ERROR.into_response())
        }
        None if path != "index.html" => serve("index.html"),
        None => StatusCode::NOT_FOUND.into_response(),
    }
}
