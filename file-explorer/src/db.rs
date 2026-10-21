use sqlx::{PgPool, postgres::PgPoolOptions};
use thiserror::Error;

use crate::config::{Config, ConfigError};

#[derive(Debug, Error)]
pub enum StartupError {
    #[error(transparent)]
    Config(#[from] ConfigError),

    #[error("database error: {0}")]
    Db(#[from] sqlx::Error),

    #[error(
        "hagio_admin.file does not exist in this database. Apply the schema \
         migrations first with `just db_migrate`; 013_file.sql creates it."
    )]
    SchemaMissing,

    #[error("could not bind {addr}: {source}")]
    Bind {
        addr: String,
        source: std::io::Error,
    },

    #[error("server stopped: {0}")]
    Serve(std::io::Error),
}

pub async fn connect(config: &Config) -> Result<PgPool, StartupError> {
    let pool = PgPoolOptions::new()
        .max_connections(5)
        .connect(&config.database.url)
        .await?;

    // The schema lives in db/migrations/, so there is no migration runner here.
    // Just check the table exists and say what to run if it does not.
    let present: bool = sqlx::query_scalar("SELECT to_regclass('hagio_admin.file') IS NOT NULL")
        .fetch_one(&pool)
        .await?;
    if !present {
        return Err(StartupError::SchemaMissing);
    }

    reconcile_link_hosts(&pool, &config.link_hosts).await?;
    Ok(pool)
}

/// Copy the configured hosts into `hagio_admin.file_link_host`, where the
/// trigger reads them. Keeps the host list in config.toml only.
async fn reconcile_link_hosts(pool: &PgPool, hosts: &[String]) -> Result<(), sqlx::Error> {
    let mut tx = pool.begin().await?;

    sqlx::query(
        "INSERT INTO hagio_admin.file_link_host (host)
         SELECT unnest($1::text[]) ON CONFLICT (host) DO NOTHING",
    )
    .bind(hosts)
    .execute(&mut *tx)
    .await?;

    let removed =
        sqlx::query("DELETE FROM hagio_admin.file_link_host WHERE host <> ALL($1::text[])")
            .bind(hosts)
            .execute(&mut *tx)
            .await?
            .rows_affected();

    tx.commit().await?;

    tracing::info!(hosts = %hosts.join(", "), removed, "link hosts reconciled");
    Ok(())
}
