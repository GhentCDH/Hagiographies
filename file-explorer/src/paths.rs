//! Every path from the outside goes through here first. Two separate things:
//!
//! Safety, in [`RelPath::parse`], runs on every incoming path. It rejects
//! anything that could point outside the share: `..`, backslashes, NUL and
//! control bytes, empty steps, and the excluded top level directories. Then
//! [`resolve`] canonicalises and checks the result is still under the root,
//! which is what catches a symlink someone else put on the share.
//!
//! Naming policy, in [`validate_name`], runs only on names we are about to
//! create. It is stricter because researchers open this share in Windows
//! Explorer. It is not applied to paths that already exist, so a file that
//! arrived over SMB with an awkward name can still be listed and renamed.

use std::path::{Component, Path, PathBuf};

use thiserror::Error;

/// Longest single path component. 255 bytes is the limit on both ext4 and SMB.
const MAX_NAME_BYTES: usize = 255;

/// Names Windows cannot open, whatever the extension.
const RESERVED_NAMES: &[&str] = &[
    "CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8",
    "COM9", "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
];

#[derive(Debug, Error, PartialEq, Eq)]
pub enum PathError {
    #[error("the name is empty")]
    Empty,
    #[error("'{0}' is too long (over {MAX_NAME_BYTES} bytes)")]
    TooLong(String),
    #[error("'{0}' cannot contain the character '{1}'")]
    BadCharacter(String, char),
    #[error("'{0}' is not allowed as a name")]
    BadName(String),
    #[error("'{0}' is a name Windows reserves and cannot open")]
    ReservedName(String),
    #[error("a name cannot start or end with a space, or end with a dot")]
    BadPadding,
    #[error("a name cannot start with a dot")]
    HiddenName,
    #[error("paths are relative to the share root and cannot contain '..' or empty steps")]
    Malformed,
    #[error("'{0}' is not part of the managed share")]
    Excluded(String),
    #[error("that path is outside the share")]
    Escapes,
    #[error("'{0}' does not exist on the share")]
    Missing(String),
}

/// A path relative to the share root, `/`-separated, no leading or trailing
/// slash, checked so it cannot address anything outside the share. The empty
/// string is the root.
#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct RelPath(String);

impl RelPath {
    pub fn root() -> Self {
        RelPath(String::new())
    }

    /// Parse an incoming path. Safety checks only, see the module docs.
    pub fn parse(raw: &str, excluded: &[String]) -> Result<Self, PathError> {
        let trimmed = raw.trim_matches('/');
        if trimmed.is_empty() {
            return Ok(Self::root());
        }
        // A backslash separates paths on Windows and SMB, so `..\x` has to be
        // refused just as firmly as `../x`.
        if let Some(bad) = trimmed
            .chars()
            .find(|c| *c == '\\' || *c == '\0' || c.is_control())
        {
            return Err(PathError::BadCharacter(raw.to_string(), bad));
        }

        let mut segments = Vec::new();
        for segment in trimmed.split('/') {
            // An interior `//`; a leading or trailing one was trimmed above.
            if segment.is_empty() || segment == "." || segment == ".." {
                return Err(PathError::Malformed);
            }
            segments.push(segment);
        }

        if let Some(first) = segments.first()
            && excluded.iter().any(|e| e == first)
        {
            return Err(PathError::Excluded((*first).to_string()));
        }

        Ok(RelPath(segments.join("/")))
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }

    pub fn is_root(&self) -> bool {
        self.0.is_empty()
    }

    /// Depth below the root: the root is 0, `a/b` is 2.
    pub fn depth(&self) -> usize {
        if self.is_root() {
            0
        } else {
            self.0.split('/').count()
        }
    }

    pub fn segments(&self) -> impl Iterator<Item = &str> {
        self.0.split('/').filter(|s| !s.is_empty())
    }

    pub fn file_name(&self) -> Option<&str> {
        if self.is_root() {
            None
        } else {
            self.0.rsplit('/').next()
        }
    }

    pub fn parent(&self) -> Option<RelPath> {
        if self.is_root() {
            return None;
        }
        Some(match self.0.rfind('/') {
            Some(i) => RelPath(self.0[..i].to_string()),
            None => Self::root(),
        })
    }

    /// Append the name of something that already exists on the share.
    pub fn join(&self, name: &str, excluded: &[String]) -> Result<RelPath, PathError> {
        if name.is_empty() || name == "." || name == ".." || name.contains('/') {
            return Err(PathError::Malformed);
        }
        if self.is_root() && excluded.iter().any(|e| e == name) {
            return Err(PathError::Excluded(name.to_string()));
        }
        Ok(if self.is_root() {
            RelPath(name.to_string())
        } else {
            RelPath(format!("{}/{}", self.0, name))
        })
    }

    /// Append a name we are about to create, applying the naming policy.
    pub fn join_new(&self, name: &str, excluded: &[String]) -> Result<RelPath, PathError> {
        validate_name(name)?;
        self.join(name, excluded)
    }

    /// This path with its last component replaced, for a rename.
    pub fn with_file_name(&self, name: &str, excluded: &[String]) -> Result<RelPath, PathError> {
        match self.parent() {
            Some(parent) => parent.join_new(name, excluded),
            None => Err(PathError::Malformed),
        }
    }

    /// True when this path is `ancestor` itself or sits below it. Used to stop a
    /// folder being moved into its own subtree.
    pub fn starts_with(&self, ancestor: &RelPath) -> bool {
        if ancestor.is_root() {
            return true;
        }
        self.0 == ancestor.0 || self.0.starts_with(&format!("{}/", ancestor.0))
    }
}

impl std::fmt::Display for RelPath {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}

/// Naming policy for something we are about to create on the share.
pub fn validate_name(name: &str) -> Result<(), PathError> {
    if name.is_empty() {
        return Err(PathError::Empty);
    }
    if name.len() > MAX_NAME_BYTES {
        return Err(PathError::TooLong(name.to_string()));
    }
    if name == "." || name == ".." {
        return Err(PathError::BadName(name.to_string()));
    }

    for ch in name.chars() {
        // `/` and `\` separate paths, `:` marks a drive or data stream on
        // Windows, NUL ends a C string, and control chars make unreadable names.
        if matches!(ch, '/' | '\\' | ':' | '\0') || ch.is_control() {
            return Err(PathError::BadCharacter(name.to_string(), ch));
        }
    }

    // Hidden entries are not listed, so creating one makes a file that
    // immediately vanishes.
    if name.starts_with('.') {
        return Err(PathError::HiddenName);
    }
    // Windows strips these silently, which turns a rename into a surprise.
    if name.starts_with(' ') || name.ends_with(' ') || name.ends_with('.') {
        return Err(PathError::BadPadding);
    }

    let stem = name.split('.').next().unwrap_or(name);
    if RESERVED_NAMES.iter().any(|r| r.eq_ignore_ascii_case(stem)) {
        return Err(PathError::ReservedName(name.to_string()));
    }

    Ok(())
}

/// True for entries the interface pretends do not exist.
pub fn is_hidden_entry(name: &str) -> bool {
    name.starts_with('.') || name.chars().any(|c| c.is_control())
}

/// Absolute path of an existing entry, proven to be inside the share.
///
/// Canonicalising resolves symlinks, so a link pointing outside the share fails
/// the containment check instead of being followed.
pub fn resolve(root: &Path, rel: &RelPath) -> Result<PathBuf, PathError> {
    let real = root
        .join(rel.as_str())
        .canonicalize()
        .map_err(|_| PathError::Missing(rel.to_string()))?;
    if !real.starts_with(root) {
        return Err(PathError::Escapes);
    }
    Ok(real)
}

/// Absolute path of an entry that does not exist yet, like an upload target or
/// a rename destination. The parent must exist and be inside the share.
pub fn resolve_new(root: &Path, rel: &RelPath) -> Result<PathBuf, PathError> {
    let parent = rel.parent().ok_or(PathError::Malformed)?;
    let name = rel.file_name().ok_or(PathError::Empty)?;
    let candidate = resolve(root, &parent)?.join(name);

    // The parent is canonical and name is a single component that cannot be
    // `..`, so nothing can traverse upwards. Assert it anyway: this function
    // guards every write we make.
    debug_assert!(
        !candidate
            .components()
            .any(|c| matches!(c, Component::ParentDir)),
        "resolve_new produced a path containing .."
    );
    Ok(candidate)
}

/// The path of `abs` relative to the share root, for the scanner.
pub fn relativise(root: &Path, abs: &Path) -> Option<RelPath> {
    let mut segments = Vec::new();
    for component in abs.strip_prefix(root).ok()?.components() {
        match component {
            Component::Normal(os) => segments.push(os.to_str()?.to_string()),
            _ => return None,
        }
    }
    Some(RelPath(segments.join("/")))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn excluded() -> Vec<String> {
        vec!["_admin".to_string()]
    }

    #[test]
    fn plain_relative_paths_are_accepted() {
        assert_eq!(
            RelPath::parse("scans/ms/a.pdf", &excluded())
                .unwrap()
                .as_str(),
            "scans/ms/a.pdf"
        );
        assert!(RelPath::parse("", &excluded()).unwrap().is_root());
        // A stray leading or trailing slash is sloppiness, not an attack.
        assert_eq!(
            RelPath::parse("/scans/", &excluded()).unwrap().as_str(),
            "scans"
        );
    }

    #[test]
    fn traversal_is_rejected() {
        for raw in [
            "..",
            "../etc/passwd",
            "scans/../../etc",
            "scans/./a",
            "a/../b",
        ] {
            assert_eq!(
                RelPath::parse(raw, &excluded()),
                Err(PathError::Malformed),
                "{raw} should have been rejected"
            );
        }
        assert_eq!(
            RelPath::parse("scans//a.pdf", &excluded()),
            Err(PathError::Malformed)
        );
    }

    #[test]
    fn backslashes_nul_and_control_characters_are_rejected() {
        assert_eq!(
            RelPath::parse(r"..\etc\passwd", &excluded()),
            Err(PathError::BadCharacter(r"..\etc\passwd".into(), '\\'))
        );
        assert!(RelPath::parse("a\0b", &excluded()).is_err());
        assert!(RelPath::parse("a\nb", &excluded()).is_err());
    }

    #[test]
    fn an_absolute_path_cannot_survive_parsing() {
        // The leading slash is trimmed, so what is left is relative by
        // construction and `resolve` joins it under the root.
        assert_eq!(
            RelPath::parse("/etc/passwd", &excluded()).unwrap().as_str(),
            "etc/passwd"
        );
        let root = tempfile::tempdir().unwrap();
        let root = root.path().canonicalize().unwrap();
        assert!(matches!(
            resolve(&root, &RelPath::parse("/etc/passwd", &excluded()).unwrap()),
            Err(PathError::Missing(_))
        ));
    }

    #[test]
    fn naming_policy_rejects_windows_hostile_names() {
        for name in ["CON", "nul", "com1", "LPT9.txt", "Aux.pdf"] {
            assert!(
                matches!(validate_name(name), Err(PathError::ReservedName(_))),
                "{name} should have been rejected"
            );
        }
        assert!(validate_name("console.pdf").is_ok());

        assert_eq!(validate_name(" a.pdf"), Err(PathError::BadPadding));
        assert_eq!(validate_name("a.pdf "), Err(PathError::BadPadding));
        assert_eq!(validate_name("a."), Err(PathError::BadPadding));
        assert_eq!(validate_name(".hidden"), Err(PathError::HiddenName));
        assert_eq!(
            validate_name("C:stream"),
            Err(PathError::BadCharacter("C:stream".into(), ':'))
        );
        assert_eq!(
            validate_name("a/b"),
            Err(PathError::BadCharacter("a/b".into(), '/'))
        );
        assert!(matches!(
            validate_name(&"x".repeat(MAX_NAME_BYTES + 1)),
            Err(PathError::TooLong(_))
        ));
        assert!(validate_name(&"x".repeat(MAX_NAME_BYTES)).is_ok());
    }

    #[test]
    fn naming_policy_does_not_apply_to_paths_already_on_the_share() {
        // A file that arrived over SMB with a Windows-hostile name must still be
        // listable and renameable, or it is stuck forever.
        assert!(RelPath::parse("scans/CON.pdf", &excluded()).is_ok());
        assert!(RelPath::parse("scans/trailing. ", &excluded()).is_ok());
        assert_eq!(
            RelPath::parse("scans", &excluded())
                .unwrap()
                .join("CON.pdf", &excluded())
                .unwrap()
                .as_str(),
            "scans/CON.pdf"
        );
        // ...but renaming it to another bad name is refused.
        assert!(
            RelPath::parse("scans/CON.pdf", &excluded())
                .unwrap()
                .with_file_name("NUL.pdf", &excluded())
                .is_err()
        );
    }

    #[test]
    fn excluded_top_level_directory_is_rejected_but_not_deeper_namesakes() {
        assert_eq!(
            RelPath::parse("_admin", &excluded()),
            Err(PathError::Excluded("_admin".into()))
        );
        assert_eq!(
            RelPath::parse("_admin/secret.pdf", &excluded()),
            Err(PathError::Excluded("_admin".into()))
        );
        // Only the top level is special.
        assert!(RelPath::parse("scans/_admin/a.pdf", &excluded()).is_ok());
        // ...and nothing may create or rename its way into one.
        assert_eq!(
            RelPath::root().join_new("_admin", &excluded()),
            Err(PathError::Excluded("_admin".into()))
        );
        assert!(
            RelPath::parse("scans", &excluded())
                .unwrap()
                .join_new("_admin", &excluded())
                .is_ok()
        );
    }

    #[test]
    fn parent_and_rename_behave() {
        let p = RelPath::parse("scans/ms/a.pdf", &excluded()).unwrap();
        assert_eq!(p.file_name(), Some("a.pdf"));
        assert_eq!(p.parent().unwrap().as_str(), "scans/ms");
        assert_eq!(p.depth(), 3);
        assert_eq!(
            p.with_file_name("b.pdf", &excluded()).unwrap().as_str(),
            "scans/ms/b.pdf"
        );
        assert_eq!(RelPath::root().parent(), None);
        assert_eq!(
            RelPath::parse("a", &excluded()).unwrap().parent(),
            Some(RelPath::root())
        );
    }

    #[test]
    fn starts_with_is_not_fooled_by_a_shared_prefix() {
        let scans = RelPath::parse("scans", &excluded()).unwrap();
        assert!(
            RelPath::parse("scans/a.pdf", &excluded())
                .unwrap()
                .starts_with(&scans)
        );
        assert!(scans.starts_with(&scans));
        // The case that matters: 'scans_old' is not inside 'scans'.
        assert!(
            !RelPath::parse("scans_old/a.pdf", &excluded())
                .unwrap()
                .starts_with(&scans)
        );
        assert!(
            RelPath::parse("anything", &excluded())
                .unwrap()
                .starts_with(&RelPath::root())
        );
    }

    #[test]
    fn a_symlink_out_of_the_share_does_not_resolve() {
        let root = tempfile::tempdir().unwrap();
        let outside = tempfile::tempdir().unwrap();
        std::fs::write(outside.path().join("secret.txt"), b"nope").unwrap();

        let root = root.path().canonicalize().unwrap();
        std::os::unix::fs::symlink(outside.path(), root.join("escape")).unwrap();

        assert_eq!(
            resolve(&root, &RelPath::parse("escape", &excluded()).unwrap()),
            Err(PathError::Escapes)
        );
        assert_eq!(
            resolve(
                &root,
                &RelPath::parse("escape/secret.txt", &excluded()).unwrap()
            ),
            Err(PathError::Escapes)
        );
    }

    #[test]
    fn resolve_new_requires_an_existing_parent_inside_the_share() {
        let root = tempfile::tempdir().unwrap();
        let root = root.path().canonicalize().unwrap();
        std::fs::create_dir(root.join("scans")).unwrap();

        let target = RelPath::parse("scans/new.pdf", &excluded()).unwrap();
        assert_eq!(
            resolve_new(&root, &target).unwrap(),
            root.join("scans/new.pdf")
        );

        assert!(matches!(
            resolve_new(&root, &RelPath::parse("nope/new.pdf", &excluded()).unwrap()),
            Err(PathError::Missing(_))
        ));
    }

    #[test]
    fn relativise_round_trips_scanner_paths() {
        let root = Path::new("/srv/share");
        assert_eq!(
            relativise(root, Path::new("/srv/share/scans/a.pdf"))
                .unwrap()
                .as_str(),
            "scans/a.pdf"
        );
        assert!(relativise(root, Path::new("/srv/share")).unwrap().is_root());
        assert_eq!(relativise(root, Path::new("/etc/passwd")), None);
    }

    #[test]
    fn hidden_entries_are_recognised() {
        assert!(is_hidden_entry(".DS_Store"));
        assert!(is_hidden_entry("a\u{1}b"));
        assert!(!is_hidden_entry("a.pdf"));
    }
}
