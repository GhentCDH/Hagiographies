use axum::{
    Json,
    extract::{Multipart, Path, State},
};
use serde::{Deserialize, Serialize};
use tokio::io::AsyncWriteExt;
use uuid::Uuid;

use crate::error::{AppError, AppResult};
use crate::fs_ops;
use crate::paths::{self, RelPath};
use crate::state::AppState;
use crate::tree;
use crate::undo::{Step, Who};

#[derive(Debug, Serialize)]
pub struct FileResponse {
    file_id: Uuid,
    path: String,
    name: String,
    link: String,
}

impl FileResponse {
    fn new(state: &AppState, file_id: Uuid, path: &RelPath) -> Self {
        FileResponse {
            file_id,
            path: path.as_str().to_string(),
            name: path.file_name().unwrap_or_default().to_string(),
            link: state.config.link_for(file_id),
        }
    }
}

/// Where a tracked file currently sits.
async fn fetch(state: &AppState, file_id: Uuid) -> AppResult<RelPath> {
    tree::file_path(&state.pool, file_id)
        .await?
        .ok_or_else(|| AppError::NotFound("no file is tracked under that id".to_string()))
}

/// Move a tracked file and record where it went.
///
/// The file moves first and the row follows. If the row cannot be written the
/// move is undone, because a row that disagrees with the share breaks every
/// link resolving through it.
pub(crate) async fn move_file(
    state: &AppState,
    file_id: Uuid,
    from_rel: &RelPath,
    to_rel: &RelPath,
    verb: &'static str,
) -> AppResult<()> {
    let root = &state.config.share_root;
    let from = paths::resolve(root, from_rel)?;
    let to = paths::resolve_new(root, to_rel)?;

    fs_ops::rename(&from, &to)?;

    // Where it went is a folder and a name now, not a path, so the write is the
    // same size whether this is a rename, a move, or both at once.
    let directory_id = match to_rel.parent() {
        Some(parent) => tree::ensure_dir(&state.pool, &parent).await?,
        None => tree::root_id(&state.pool).await?,
    };
    let written = sqlx::query(
        "UPDATE hagio_admin.file
         SET directory_id = $1, name = $2, missing_since = NULL, updated_at = now()
         WHERE file_id = $3",
    )
    .bind(directory_id)
    .bind(to_rel.file_name().unwrap_or_default())
    .bind(file_id)
    .execute(&state.pool)
    .await;

    if let Err(error) = written {
        if let Err(undo) = std::fs::rename(&to, &from) {
            tracing::error!(
                from = %from.display(), to = %to.display(),
                "could not undo a move after the database write failed: {undo}"
            );
        }
        // A stale row can still hold the destination name in that folder, from a
        // file deleted over SMB and later recreated under the same name.
        if error.as_database_error().and_then(|e| e.code()).as_deref() == Some("23505") {
            return Err(AppError::Conflict(format!(
                "another tracked file already claims '{to_rel}'; rescan the share and try again"
            )));
        }
        return Err(error.into());
    }

    tracing::info!(file_id = %file_id, from = %from_rel, to = %to_rel, "file {verb}");
    Ok(())
}

#[derive(Debug, Deserialize)]
pub struct RenameBody {
    pub name: String,
}

pub async fn rename(
    State(state): State<AppState>,
    who: Who,
    Path(file_id): Path<Uuid>,
    Json(body): Json<RenameBody>,
) -> AppResult<Json<FileResponse>> {
    let excluded = &state.config.excluded_dirs;
    let current = fetch(&state, file_id).await?;
    let target = current.with_file_name(body.name.trim(), excluded)?;

    if target != current {
        let old_name = current.file_name().unwrap_or_default().to_string();
        move_file(&state, file_id, &current, &target, "renamed").await?;
        state
            .undo
            .push(
                &who,
                format!("renaming '{current}' to '{target}'"),
                Step::FileRenamed { file_id, old_name },
            )
            .await;
    }
    Ok(Json(FileResponse::new(&state, file_id, &target)))
}

#[derive(Debug, Deserialize)]
pub struct MoveBody {
    pub dest_dir: String,
}

pub async fn move_to(
    State(state): State<AppState>,
    who: Who,
    Path(file_id): Path<Uuid>,
    Json(body): Json<MoveBody>,
) -> AppResult<Json<FileResponse>> {
    let config = &state.config;
    let excluded = &config.excluded_dirs;
    let current = fetch(&state, file_id).await?;
    let name = current
        .file_name()
        .ok_or_else(|| AppError::BadRequest("that file has no name to move".to_string()))?;

    let dest_dir = RelPath::parse(&body.dest_dir, excluded)?;
    if !paths::resolve(&config.share_root, &dest_dir)?.is_dir() {
        return Err(AppError::BadRequest(format!(
            "'{dest_dir}' is not a directory"
        )));
    }

    let target = dest_dir.join(name, excluded)?;
    if target != current {
        let old_directory_id = match current.parent() {
            Some(parent) => tree::ensure_dir(&state.pool, &parent).await?,
            None => tree::root_id(&state.pool).await?,
        };
        move_file(&state, file_id, &current, &target, "moved").await?;
        state
            .undo
            .push(
                &who,
                format!("moving '{current}' to '{dest_dir}'"),
                Step::FileMoved {
                    file_id,
                    old_directory_id,
                },
            )
            .await;
    }
    Ok(Json(FileResponse::new(&state, file_id, &target)))
}

/// `multipart/form-data` with `dir`, `name` and then `file`, in that order.
///
/// The order matters: the body is read as a stream, so the destination has to
/// be known before the bytes arrive.
pub async fn upload(
    State(state): State<AppState>,
    who: Who,
    mut multipart: Multipart,
) -> AppResult<Json<FileResponse>> {
    let config = &state.config;
    let excluded = &config.excluded_dirs;

    let mut dir: Option<RelPath> = None;
    let mut name: Option<String> = None;

    while let Some(mut field) = multipart.next_field().await.map_err(upload_failed)? {
        match field.name().unwrap_or_default() {
            "dir" => {
                let raw = field.text().await.map_err(upload_failed)?;
                dir = Some(RelPath::parse(&raw, excluded)?);
            }
            "name" => {
                name = Some(
                    field
                        .text()
                        .await
                        .map_err(upload_failed)?
                        .trim()
                        .to_string(),
                );
            }
            "file" => {
                let dir = dir.clone().ok_or_else(|| {
                    AppError::BadRequest(
                        "the upload did not say which directory to use".to_string(),
                    )
                })?;
                let name = name.clone().ok_or_else(|| {
                    AppError::BadRequest("the upload did not say what to call the file".to_string())
                })?;

                let target_rel = dir.join_new(&name, excluded)?;
                let target = paths::resolve_new(&config.share_root, &target_rel)?;
                if target.symlink_metadata().is_ok() {
                    return Err(AppError::Conflict(format!(
                        "'{name}' already exists here, pick another name"
                    )));
                }

                // Written beside the target so the final rename is atomic and
                // nobody sees a half-uploaded file at the real path.
                let temp = fs_ops::temp_path_beside(&target);
                let size = match stream_to_file(&mut field, &temp).await {
                    Ok(size) => size,
                    Err(e) => {
                        let _ = std::fs::remove_file(&temp);
                        return Err(e);
                    }
                };
                if let Err(e) = fs_ops::rename(&temp, &target) {
                    let _ = std::fs::remove_file(&temp);
                    return Err(e);
                }

                let file_id = match insert_row(&state, &target_rel, size, &name).await {
                    Ok(id) => id,
                    Err(e) => {
                        // An untracked file is invisible until the next scan,
                        // so do not leave one behind on a failed insert.
                        let _ = std::fs::remove_file(&target);
                        return Err(e);
                    }
                };

                tracing::info!(path = %target_rel, size, "uploaded");
                let step = Step::FilesAdded {
                    files: vec![(file_id, size)],
                    root: None,
                };
                state
                    .undo
                    .push(&who, format!("uploading '{target_rel}'"), step)
                    .await;
                return Ok(Json(FileResponse::new(&state, file_id, &target_rel)));
            }
            other => {
                return Err(AppError::BadRequest(format!(
                    "the upload contained an unexpected field '{other}'"
                )));
            }
        }
    }

    Err(AppError::BadRequest(
        "the upload contained no file".to_string(),
    ))
}

async fn stream_to_file(
    field: &mut axum::extract::multipart::Field<'_>,
    temp: &std::path::Path,
) -> AppResult<i64> {
    let mut out = tokio::fs::File::create(temp).await?;
    let mut size: i64 = 0;

    while let Some(chunk) = field.chunk().await.map_err(upload_failed)? {
        size += chunk.len() as i64;
        out.write_all(&chunk).await?;
    }
    out.flush().await?;

    Ok(size)
}

async fn insert_row(state: &AppState, rel: &RelPath, size: i64, name: &str) -> AppResult<Uuid> {
    let directory_id = match rel.parent() {
        Some(parent) => tree::ensure_dir(&state.pool, &parent).await?,
        None => tree::root_id(&state.pool).await?,
    };
    let file_id = sqlx::query_scalar::<_, Uuid>(
        "INSERT INTO hagio_admin.file (directory_id, name, size_bytes, content_type)
         VALUES ($1, $2, $3, $4)
         ON CONFLICT (directory_id, name) DO UPDATE
         SET size_bytes = EXCLUDED.size_bytes,
             content_type = EXCLUDED.content_type,
             missing_since = NULL,
             updated_at = now()
         RETURNING file_id",
    )
    .bind(directory_id)
    .bind(name)
    .bind(size)
    .bind(fs_ops::guess_content_type(name))
    .fetch_one(&state.pool)
    .await?;

    Ok(file_id)
}

/// Multipart failures are the client's problem, like a truncated body or one
/// over max_upload_bytes, so report them instead of logging a 500.
fn upload_failed(error: axum::extract::multipart::MultipartError) -> AppError {
    AppError::BadRequest(format!("the upload could not be read: {error}"))
}

#[derive(Debug, Serialize)]
pub struct FolderResponse {
    path: String,
    name: String,
    files_uploaded: usize,
    /// Files left out, with the reason. OS junk and names we will not create.
    skipped: Vec<String>,
}

/// Upload a whole folder. `parent`, then `name`, then one `file` part per file
/// whose multipart filename is its path inside the folder.
///
/// Only the folder is named by the user. The files keep the names they came with,
/// so the naming rules are applied leniently here: a file we would refuse to
/// create is skipped and reported rather than failing the whole upload.
pub async fn upload_folder(
    State(state): State<AppState>,
    who: Who,
    mut multipart: Multipart,
) -> AppResult<Json<FolderResponse>> {
    let config = &state.config;
    let excluded = &config.excluded_dirs;

    let parent = RelPath::parse(&text_field(&mut multipart, "parent").await?, excluded)?;
    // Same rule as creating a folder by hand: the top level layout is fixed.
    if parent.is_root() {
        return Err(AppError::BadRequest(
            "folders can only be uploaded into an existing folder, not at the top level of the share"
                .to_string(),
        ));
    }
    let name = text_field(&mut multipart, "name").await?;

    let root_rel = parent.join_new(name.trim(), excluded)?;
    let root_abs = paths::resolve_new(&config.share_root, &root_rel)?;
    fs_ops::create_dir(&root_abs)?;

    match receive_folder(&mut multipart, &root_rel, &root_abs).await {
        Ok((files, skipped)) => {
            let files_uploaded = files.len();

            // Leaving an empty folder behind after an upload that put nothing in
            // it is just litter, and the reasons are more useful as an error.
            if files_uploaded == 0 {
                let _ = std::fs::remove_dir_all(&root_abs);
                return Err(AppError::BadRequest(if skipped.is_empty() {
                    "the upload contained no files".to_string()
                } else {
                    format!("nothing could be uploaded: {}", skipped.join("; "))
                }));
            }

            let uploaded = match insert_rows(&state, &files).await {
                Ok(uploaded) => uploaded,
                Err(e) => {
                    // We made this directory, so nothing else can be in it.
                    let _ = std::fs::remove_dir_all(&root_abs);
                    return Err(e);
                }
            };
            let root_id = tree::ensure_dir(&state.pool, &root_rel).await?;
            tracing::info!(
                path = %root_rel, files_uploaded, skipped = skipped.len(),
                "folder uploaded"
            );
            let step = Step::FilesAdded {
                files: uploaded,
                root: Some(root_id),
            };
            state
                .undo
                .push(&who, format!("uploading the folder '{root_rel}'"), step)
                .await;
            Ok(Json(FolderResponse {
                path: root_rel.as_str().to_string(),
                name: root_rel.file_name().unwrap_or_default().to_string(),
                files_uploaded,
                skipped,
            }))
        }
        Err(e) => {
            let _ = std::fs::remove_dir_all(&root_abs);
            Err(e)
        }
    }
}

/// Read the next part, which must be the named text field.
async fn text_field(multipart: &mut Multipart, expected: &str) -> AppResult<String> {
    let field = multipart
        .next_field()
        .await
        .map_err(upload_failed)?
        .ok_or_else(|| AppError::BadRequest(format!("the upload is missing '{expected}'")))?;

    if field.name().unwrap_or_default() != expected {
        return Err(AppError::BadRequest(format!(
            "the upload should send '{expected}' before its files"
        )));
    }
    field.text().await.map_err(upload_failed)
}

type Uploaded = (RelPath, i64, Option<String>);

/// Write every remaining part under `root_abs`. Rows are inserted afterwards, so
/// a failure here leaves nothing in the database to undo.
async fn receive_folder(
    multipart: &mut Multipart,
    root_rel: &RelPath,
    root_abs: &std::path::Path,
) -> AppResult<(Vec<Uploaded>, Vec<String>)> {
    let mut files = Vec::new();
    let mut skipped = Vec::new();

    while let Some(mut field) = multipart.next_field().await.map_err(upload_failed)? {
        if field.name().unwrap_or_default() != "file" {
            return Err(AppError::BadRequest(
                "a folder upload may only contain 'parent', 'name' and files".to_string(),
            ));
        }

        let inner_raw = field.file_name().unwrap_or_default().to_string();
        let inner = match inner_path(&inner_raw) {
            Ok(inner) => inner,
            Err(reason) => {
                // The part still has to be consumed or the stream desyncs.
                while field.chunk().await.map_err(upload_failed)?.is_some() {}
                skipped.push(format!("{inner_raw}: {reason}"));
                continue;
            }
        };

        let abs = root_abs.join(inner.as_str());
        if let Some(dir) = abs.parent() {
            tokio::fs::create_dir_all(dir).await?;
            // inner has no `..` and root_abs is canonical, so this cannot escape.
            // Checked anyway: it is the guard on a write.
            if !dir.canonicalize()?.starts_with(root_abs) {
                return Err(AppError::Path(crate::paths::PathError::Escapes));
            }
        }

        let size = stream_to_file(&mut field, &abs).await?;
        let rel = RelPath::parse(&format!("{root_rel}/{inner}"), &[])?;
        let content_type = inner.file_name().and_then(fs_ops::guess_content_type);
        files.push((rel, size, content_type));
    }

    Ok((files, skipped))
}

/// A file's path inside the uploaded folder, or why it is being left out.
fn inner_path(raw: &str) -> Result<RelPath, String> {
    if raw.is_empty() {
        return Err("it has no name".to_string());
    }
    let path = RelPath::parse(raw, &[]).map_err(|e| e.to_string())?;
    if path.is_root() {
        return Err("it has no name".to_string());
    }

    for segment in path.segments() {
        // .DS_Store, Thumbs.db's friends, and anything else the interface would
        // refuse to show or create.
        if segment.starts_with('.') {
            return Err("hidden files are not kept".to_string());
        }
        crate::paths::validate_name(segment).map_err(|e| e.to_string())?;
    }
    Ok(path)
}

/// Insert a row per uploaded file, grouped by the folder each one landed in so a
/// nested upload is one statement per folder rather than one per file.
///
/// Returns each id with its size, which is what undo needs to check the file is
/// still byte for byte as uploaded. Paired up by name rather than by position:
/// `RETURNING` makes no promise about the order it hands rows back in.
async fn insert_rows(state: &AppState, files: &[Uploaded]) -> AppResult<Vec<(Uuid, i64)>> {
    let mut by_dir: std::collections::HashMap<RelPath, Vec<&Uploaded>> =
        std::collections::HashMap::new();
    for file in files {
        by_dir
            .entry(file.0.parent().unwrap_or_else(RelPath::root))
            .or_default()
            .push(file);
    }

    let mut uploaded = Vec::with_capacity(files.len());
    for (dir, group) in by_dir {
        let directory_id = tree::ensure_dir(&state.pool, &dir).await?;
        let names: Vec<&str> = group
            .iter()
            .map(|(rel, _, _)| rel.file_name().unwrap_or_default())
            .collect();
        let sizes: Vec<i64> = group.iter().map(|(_, size, _)| *size).collect();
        let types: Vec<Option<String>> = group.iter().map(|(_, _, t)| t.clone()).collect();

        let inserted = sqlx::query_as::<_, (Uuid, String)>(
            "INSERT INTO hagio_admin.file (directory_id, name, size_bytes, content_type)
             SELECT $1, * FROM unnest($2::text[], $3::bigint[], $4::text[])
             ON CONFLICT (directory_id, name) DO UPDATE
             SET size_bytes = EXCLUDED.size_bytes,
                 content_type = EXCLUDED.content_type,
                 missing_since = NULL,
                 updated_at = now()
             RETURNING file_id, name",
        )
        .bind(directory_id)
        .bind(&names)
        .bind(&sizes)
        .bind(&types)
        .fetch_all(&state.pool)
        .await?;

        for (file_id, name) in inserted {
            let size = group
                .iter()
                .find(|(rel, _, _)| rel.file_name() == Some(name.as_str()))
                .map(|(_, size, _)| *size)
                .unwrap_or_default();
            uploaded.push((file_id, size));
        }
    }

    Ok(uploaded)
}
