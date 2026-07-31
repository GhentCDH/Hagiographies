use std::sync::Arc;

use sqlx::PgPool;

use crate::config::Config;
use crate::undo::UndoStack;

#[derive(Clone)]
pub struct AppState {
    pub pool: PgPool,
    pub config: Arc<Config>,
    /// Held during a full scan so two cannot overlap.
    pub scan_lock: Arc<tokio::sync::Mutex<()>>,
    /// What the undo button would reverse, newest last.
    pub undo: Arc<UndoStack>,
}
