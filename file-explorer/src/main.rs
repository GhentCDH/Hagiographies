mod config;
mod db;
mod embed;
mod error;
mod fs_ops;
mod models;
mod paths;
mod routes;
mod scan;
mod state;
mod undo;

use std::sync::Arc;

use crate::config::Config;
use crate::db::StartupError;
use crate::state::AppState;

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "file_explorer=info,tower_http=info".into()),
        )
        .init();

    if let Err(e) = run().await {
        eprintln!("{e}");
        std::process::exit(2);
    }
}

async fn run() -> Result<(), StartupError> {
    let config = Arc::new(Config::load()?);
    let pool = db::connect(&config).await?;

    let state = AppState {
        pool,
        config: Arc::clone(&config),
        scan_lock: Arc::new(tokio::sync::Mutex::new(())),
        undo: Arc::new(undo::UndoStack::default()),
    };

    if config.scan_on_startup {
        spawn_startup_scan(state.clone());
    }

    let listener = tokio::net::TcpListener::bind(&config.bind_addr)
        .await
        .map_err(|source| StartupError::Bind {
            addr: config.bind_addr.clone(),
            source,
        })?;

    tracing::info!(
        share_root = %config.share_root.display(),
        public_base_url = %config.public_base_url,
        "listening on http://{}", config.bind_addr
    );

    axum::serve(listener, routes::build(state))
        .await
        .map_err(StartupError::Serve)
}

/// In the background, so a slow network share does not hold up the listener.
fn spawn_startup_scan(state: AppState) {
    tokio::spawn(async move {
        let Ok(_guard) = state.scan_lock.try_lock() else {
            return;
        };
        tracing::info!("scanning the share");

        match scan::full_scan(
            &state.pool,
            &state.config.share_root,
            &state.config.excluded_dirs,
        )
        .await
        {
            Ok(summary) => tracing::info!(
                directories = summary.directories,
                files = summary.files,
                newly_missing = summary.missing,
                "scan complete"
            ),
            Err(e) => tracing::error!("scan failed: {e}"),
        }
    });
}
