use axum::{
    Json,
    http::StatusCode,
    response::{IntoResponse, Response},
};
use serde_json::json;

use crate::paths::PathError;

#[derive(thiserror::Error, Debug)]
pub enum AppError {
    #[error("database error: {0}")]
    Db(#[from] sqlx::Error),

    #[error("{0}")]
    NotFound(String),

    /// Understood and refused. These messages are shown to the student as they
    /// are, so they say what to do differently.
    #[error("{0}")]
    BadRequest(String),

    /// Something already exists at the destination. Never overwrite.
    #[error("{0}")]
    Conflict(String),

    #[error("io error: {0}")]
    Io(#[from] std::io::Error),

    #[error(transparent)]
    Path(#[from] PathError),
}

impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        let (status, message) = match &self {
            AppError::NotFound(m) => (StatusCode::NOT_FOUND, m.clone()),
            AppError::BadRequest(m) => (StatusCode::BAD_REQUEST, m.clone()),
            AppError::Conflict(m) => (StatusCode::CONFLICT, m.clone()),

            // Path errors are the client's doing and safe to repeat back: they
            // name a character or a rule, never a filesystem layout.
            AppError::Path(PathError::Missing(_)) => (StatusCode::NOT_FOUND, self.to_string()),
            AppError::Path(_) => (StatusCode::BAD_REQUEST, self.to_string()),

            AppError::Io(e) => {
                tracing::error!("io error: {e}");
                (
                    StatusCode::INTERNAL_SERVER_ERROR,
                    "could not complete the operation on the share".to_string(),
                )
            }
            AppError::Db(e) => {
                tracing::error!("db error: {e}");
                (
                    StatusCode::INTERNAL_SERVER_ERROR,
                    "database error".to_string(),
                )
            }
        };

        (status, Json(json!({ "error": message }))).into_response()
    }
}

pub type AppResult<T> = Result<T, AppError>;
