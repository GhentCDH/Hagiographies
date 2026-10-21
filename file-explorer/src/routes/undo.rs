use axum::{Json, extract::State};
use serde::Serialize;

use crate::error::{AppError, AppResult};
use crate::state::AppState;
use crate::undo::{self, Who};

#[derive(Debug, Serialize)]
pub struct Available {
    /// What the next undo would reverse, or null when there is nothing to undo.
    label: Option<String>,
}

pub async fn peek(State(state): State<AppState>, who: Who) -> Json<Available> {
    Json(Available {
        label: state.undo.peek(&who).await.map(|entry| entry.label),
    })
}

#[derive(Debug, Serialize)]
pub struct Done {
    done: String,
}

pub async fn perform(State(state): State<AppState>, who: Who) -> AppResult<Json<Done>> {
    let entry = state
        .undo
        .pop(&who)
        .await
        .ok_or_else(|| AppError::BadRequest("there is nothing to undo".to_string()))?;

    match undo::apply(&state, &entry.step).await {
        Ok(done) => Ok(Json(Done { done })),
        Err(e) => {
            // A refusal is not the user losing their undo: the operation is still
            // the last thing they did, so put it back on the stack.
            state.undo.restore(&who, entry).await;
            Err(e)
        }
    }
}
