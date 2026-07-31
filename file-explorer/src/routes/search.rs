//! Fuzzy search over every tracked file.
//!
//! `hagio_admin.file` is a full inventory of the share, so the search reads the
//! table rather than walking the filesystem. Postgres does the cheap part with an
//! ILIKE built from the query letters spread out with wildcards, which is exactly
//! a subsequence test. Whatever survives that is scored and ranked here, where we
//! can be picky about it.
//!
//! Folders are not searched: they have no rows of their own. The folder of each
//! hit is returned so you can jump there.

use axum::{
    Json,
    extract::{Query, State},
};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

use crate::error::AppResult;
use crate::paths::RelPath;
use crate::state::AppState;

/// How many rows the database may hand back before we rank them. Well past any
/// query anyone would read the results of.
const CANDIDATE_LIMIT: i64 = 5_000;

/// How many hits the interface gets.
const RESULT_LIMIT: usize = 50;

#[derive(Debug, Deserialize)]
pub struct SearchQuery {
    #[serde(default)]
    pub q: String,
}

#[derive(Debug, Serialize)]
pub struct Hit {
    file_id: Uuid,
    name: String,
    path: String,
    /// The folder it sits in, for the "go there" link.
    dir: String,
    link: String,
    size_bytes: Option<i64>,
    missing: bool,
}

#[derive(Debug, Serialize)]
pub struct SearchResults {
    query: String,
    hits: Vec<Hit>,
    /// True when there were more matches than we returned.
    truncated: bool,
}

#[derive(Debug, sqlx::FromRow)]
struct Candidate {
    file_id: Uuid,
    relative_path: String,
    size_bytes: Option<i64>,
    missing_since: Option<chrono::DateTime<chrono::Utc>>,
}

pub async fn search(
    State(state): State<AppState>,
    Query(query): Query<SearchQuery>,
) -> AppResult<Json<SearchResults>> {
    let config = &state.config;
    // Whitespace is treated as nothing, so "koln 6" behaves like "koln6".
    let needle: String = query.q.chars().filter(|c| !c.is_whitespace()).collect();

    if needle.is_empty() {
        return Ok(Json(SearchResults {
            query: query.q,
            hits: Vec::new(),
            truncated: false,
        }));
    }

    let candidates = sqlx::query_as::<_, Candidate>(
        "SELECT file_id, relative_path, size_bytes, missing_since
         FROM hagio_admin.file
         WHERE relative_path ILIKE $1 ESCAPE '\\'
         LIMIT $2",
    )
    .bind(subsequence_pattern(&needle))
    .bind(CANDIDATE_LIMIT)
    .fetch_all(&state.pool)
    .await?;

    let mut scored: Vec<(i32, Hit)> = Vec::new();
    for row in candidates {
        // Skips anything under a directory that is now excluded, which the
        // scanner would no longer add but may have added before.
        let Ok(rel) = RelPath::parse(&row.relative_path, &config.excluded_dirs) else {
            continue;
        };
        let Some(score) = score(&row.relative_path, &needle) else {
            continue;
        };

        scored.push((
            score,
            Hit {
                file_id: row.file_id,
                name: rel.file_name().unwrap_or_default().to_string(),
                path: rel.as_str().to_string(),
                dir: rel
                    .parent()
                    .map(|p| p.as_str().to_string())
                    .unwrap_or_default(),
                link: config.link_for(row.file_id),
                size_bytes: row.size_bytes,
                missing: row.missing_since.is_some(),
            },
        ));
    }

    // Best first, then alphabetically so equal scores do not jump around.
    scored.sort_by(|a, b| b.0.cmp(&a.0).then_with(|| a.1.path.cmp(&b.1.path)));

    let truncated = scored.len() > RESULT_LIMIT;
    let hits = scored
        .into_iter()
        .take(RESULT_LIMIT)
        .map(|(_, hit)| hit)
        .collect();

    Ok(Json(SearchResults {
        query: query.q,
        hits,
        truncated,
    }))
}

/// `kl6` becomes `%k%l%6%`, which ILIKE evaluates as "these letters in this
/// order, with anything in between".
fn subsequence_pattern(needle: &str) -> String {
    let mut out = String::with_capacity(needle.len() * 2 + 1);
    out.push('%');
    for ch in needle.chars() {
        if matches!(ch, '\\' | '%' | '_') {
            out.push('\\');
        }
        out.push(ch);
        out.push('%');
    }
    out
}

/// How well `path` matches `needle`, or None if it does not.
///
/// A match in the file name is what people mean almost every time, so that is
/// tried first and scored well above a match that had to wander through the
/// directories to find its letters.
fn score(path: &str, needle: &str) -> Option<i32> {
    let name_start = path.rfind('/').map(|i| i + 1).unwrap_or(0);
    let name = &path[name_start..];

    let in_name = subsequence_score(name, needle).map(|score| {
        let mut score = score + 1_000;
        // An unbroken run of the query in the name is the strongest signal there
        // is, so say so loudly.
        if name.to_lowercase().contains(&needle.to_lowercase()) {
            score += 500;
        }
        score
    });

    let best = match in_name {
        Some(score) => score,
        None => subsequence_score(path, needle)?,
    };

    // Shorter paths first when everything else is equal: they are nearer the top
    // of the share and easier to recognise.
    Some(best - (path.len() as i32) / 8)
}

/// Greedy left to right subsequence match with bonuses for matches that land
/// where a person would look: consecutive letters, and the start of a word.
fn subsequence_score(haystack: &str, needle: &str) -> Option<i32> {
    let hay: Vec<char> = haystack.chars().collect();
    let hay_lower: Vec<char> = haystack.to_lowercase().chars().collect();
    let want: Vec<char> = needle.to_lowercase().chars().collect();

    let mut score = 0;
    let mut at = 0usize;
    let mut previous: Option<usize> = None;

    for ch in want {
        let found = (at..hay_lower.len()).find(|i| hay_lower[*i] == ch)?;

        score += 10;
        if previous == Some(found.wrapping_sub(1)) {
            score += 15;
        } else if found == 0 || is_boundary(&hay, found) {
            score += 10;
        }
        if let Some(prev) = previous {
            // Gaps cost a little, so tightly packed matches win.
            score -= ((found - prev - 1) as i32).min(10);
        }

        previous = Some(found);
        at = found + 1;
    }

    Some(score)
}

/// True when `hay[i]` starts a word: after a separator, or a lowercase to
/// uppercase step as in `KolnHA`.
fn is_boundary(hay: &[char], i: usize) -> bool {
    if i == 0 {
        return true;
    }
    let before = hay[i - 1];
    matches!(before, '/' | '-' | '_' | '.' | ' ' | '(' | ')')
        || (before.is_lowercase() && hay[i].is_uppercase())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pattern_spreads_the_letters_and_escapes_wildcards() {
        assert_eq!(subsequence_pattern("kl6"), "%k%l%6%");
        assert_eq!(subsequence_pattern("50%"), r"%5%0%\%%");
        assert_eq!(subsequence_pattern("a_b"), r"%a%\_%b%");
    }

    #[test]
    fn letters_out_of_order_do_not_match() {
        assert!(score("scans/koln-6.pdf", "6koln").is_none());
        assert!(score("scans/koln-6.pdf", "zzz").is_none());
    }

    #[test]
    fn scattered_letters_match() {
        assert!(score("scans/koln-6-plate.jpg", "kln6").is_some());
        assert!(score("scans/koln-6-plate.jpg", "koln6plate").is_some());
    }

    #[test]
    fn matching_is_case_insensitive() {
        assert!(score("scans/Koln-HA-6.pdf", "koln").is_some());
        assert!(score("scans/koln-ha-6.pdf", "KOLN").is_some());
    }

    #[test]
    fn a_name_match_beats_a_directory_match() {
        // 'scans' is in the directory of one and the name of the other.
        let in_dir = score("scans/koln-6.pdf", "scans").unwrap();
        let in_name = score("editions/scans-list.pdf", "scans").unwrap();
        assert!(in_name > in_dir, "{in_name} should beat {in_dir}");
    }

    #[test]
    fn a_run_beats_scattered_letters() {
        let run = score("scans/koln.pdf", "koln").unwrap();
        let scattered = score("scans/k-o-l-n.pdf", "koln").unwrap();
        assert!(run > scattered, "{run} should beat {scattered}");
    }

    #[test]
    fn word_starts_beat_letters_buried_mid_word() {
        let boundary = score("scans/koln-ha-6.pdf", "kh").unwrap();
        let buried = score("scans/xkxhx.pdf", "kh").unwrap();
        assert!(boundary > buried, "{boundary} should beat {buried}");
    }

    #[test]
    fn shorter_paths_win_a_tie() {
        let shallow = score("koln.pdf", "koln").unwrap();
        let deep = score("a/b/c/d/e/koln.pdf", "koln").unwrap();
        assert!(shallow > deep, "{shallow} should beat {deep}");
    }

    #[test]
    fn whole_query_present_ranks_top() {
        let exact = score("scans/koln-6.pdf", "koln").unwrap();
        let fuzzy = score("scans/k-oxxln-6.pdf", "koln").unwrap();
        assert!(exact > fuzzy, "{exact} should beat {fuzzy}");
    }
}
