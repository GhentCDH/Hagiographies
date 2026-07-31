//! Configuration: a `config.toml`, overridden by `FILES_*` environment vars.
//!
//! Nested keys use a double underscore, so `[database] url` is
//! `FILES_DATABASE__URL`. Lists are TOML arrays either way:
//! `FILES_EXCLUDED_DIRS='["_admin", "tmp"]'`.

use std::path::PathBuf;

use figment::{
    Figment,
    providers::{Env, Format, Toml},
};
use serde::Deserialize;
use thiserror::Error;

const DEFAULT_CONFIG_PATH: &str = "config.toml";

#[derive(Debug, Error)]
pub enum ConfigError {
    // Boxed: figment::Error is over 200 bytes, and every Result in this
    // module would carry that.
    #[error("could not read the configuration: {0}")]
    Read(Box<figment::Error>),

    #[error(
        "public_base_url '{0}' has no host, so link_hosts cannot be derived from it; \
         set link_hosts explicitly"
    )]
    NoHost(String),

    #[error("no database url; set FILES_DATABASE__URL or database.url in config.toml")]
    NoDatabaseUrl,

    #[error("share_root {path} is not usable: {source}")]
    ShareRoot {
        path: PathBuf,
        source: std::io::Error,
    },

    #[error("share_root {0} is not a directory")]
    ShareRootNotDir(PathBuf),
}

/// Kept out of the committed `config.toml`; comes from `FILES_DATABASE__URL`.
#[derive(Debug, Default, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Database {
    #[serde(default)]
    pub url: String,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Config {
    #[serde(default)]
    pub database: Database,

    /// Root of the network share. Everything the app touches is under here.
    #[serde(default = "default_share_root")]
    pub share_root: PathBuf,

    /// Public origin of this app, used to build the links students copy.
    pub public_base_url: String,

    /// Hosts whose `/f/<uuid>` URLs count as links to a tracked file. Copied
    /// into `hagio_admin.file_link_host` at startup for the database trigger.
    /// Defaults to the host of `public_base_url`.
    #[serde(default)]
    pub link_hosts: Vec<String>,

    /// Top level directory names hidden from the interface entirely: never
    /// listed, navigated, scanned or tracked.
    #[serde(default)]
    pub excluded_dirs: Vec<String>,

    #[serde(default = "default_bind_addr")]
    pub bind_addr: String,

    /// Upload ceiling. Axum's 2 MB default would reject every real scan.
    #[serde(default = "default_max_upload_bytes")]
    pub max_upload_bytes: usize,

    /// Walk the whole share at startup so the `file` table is a full inventory,
    /// not just a record of what this app uploaded.
    #[serde(default = "default_true")]
    pub scan_on_startup: bool,
}

fn default_share_root() -> PathBuf {
    PathBuf::from("/srv/share")
}

fn default_bind_addr() -> String {
    "0.0.0.0:3000".to_string()
}

fn default_max_upload_bytes() -> usize {
    2 * 1024 * 1024 * 1024
}

fn default_true() -> bool {
    true
}

impl Config {
    pub fn load() -> Result<Self, ConfigError> {
        let path =
            std::env::var("FILES_CONFIG").unwrap_or_else(|_| DEFAULT_CONFIG_PATH.to_string());

        let mut config: Config = Figment::new()
            .merge(Toml::file(&path))
            .merge(Env::prefixed("FILES_").split("__").ignore(&["CONFIG"]))
            .extract()
            .map_err(|e| ConfigError::Read(Box::new(e)))?;

        config.normalise()?;
        Ok(config)
    }

    fn normalise(&mut self) -> Result<(), ConfigError> {
        if self.database.url.trim().is_empty() {
            return Err(ConfigError::NoDatabaseUrl);
        }

        // The rest of the repo pastes PG_DATABASE_URL straight in, and that
        // value carries SQLAlchemy's driver suffix. Strip it, like
        // db/src/hagio_db/conn.py does.
        if let Some(rest) = self.database.url.strip_prefix("postgresql+psycopg://") {
            self.database.url = format!("postgresql://{rest}");
        }

        self.public_base_url = self.public_base_url.trim_end_matches('/').to_string();

        if self.link_hosts.is_empty() {
            let host = host_of(&self.public_base_url)
                .ok_or_else(|| ConfigError::NoHost(self.public_base_url.clone()))?;
            self.link_hosts = vec![host];
        }
        for host in &mut self.link_hosts {
            *host = host.trim().to_ascii_lowercase();
        }
        self.link_hosts.sort();
        self.link_hosts.dedup();

        // Resolving the root once here is what makes the containment check in
        // paths::resolve mean anything: later comparisons are against a path
        // with no symlinks and no `..` left in it.
        self.share_root =
            self.share_root
                .canonicalize()
                .map_err(|source| ConfigError::ShareRoot {
                    path: self.share_root.clone(),
                    source,
                })?;
        if !self.share_root.is_dir() {
            return Err(ConfigError::ShareRootNotDir(self.share_root.clone()));
        }

        Ok(())
    }

    /// The link a student copies for a file.
    pub fn link_for(&self, file_id: uuid::Uuid) -> String {
        format!("{}/f/{}", self.public_base_url, file_id)
    }
}

/// Host of an `http(s)://host[:port]/...` URL, lowercased, without the port.
fn host_of(url: &str) -> Option<String> {
    let rest = url
        .strip_prefix("https://")
        .or_else(|| url.strip_prefix("http://"))?;
    let host = rest.split('/').next()?.split(':').next()?;
    if host.is_empty() {
        None
    } else {
        Some(host.to_ascii_lowercase())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn host_is_extracted_without_scheme_or_port() {
        assert_eq!(
            host_of("https://Files.M-Patch.ugent.be"),
            Some("files.m-patch.ugent.be".into())
        );
        assert_eq!(host_of("http://localhost:9161"), Some("localhost".into()));
        assert_eq!(
            host_of("http://localhost:9161/f/x"),
            Some("localhost".into())
        );
        assert_eq!(host_of("ftp://example.com"), None);
        assert_eq!(host_of("http://"), None);
    }
}
