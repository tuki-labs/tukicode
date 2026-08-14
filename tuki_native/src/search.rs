use pyo3::prelude::*;
use rayon::prelude::*;
use regex::Regex;
use std::path::Path;
use std::sync::Mutex;

use crate::DEFAULT_IGNORE;

fn should_ignore(name: &str) -> bool {
    DEFAULT_IGNORE.contains(&name)
}

/// Searches for a pattern in files under `path`.
/// Uses Rayon for parallel file search across CPU cores.
/// Respects .gitignore via the `ignore` crate when available.
/// Returns up to `max_results` matches formatted as "file:line:content".
#[pyfunction]
#[pyo3(signature = (query, path, file_extensions=None, case_sensitive=false, context_lines=2, max_results=50))]
pub fn search_code(
    query: &str,
    path: &str,
    file_extensions: Option<Vec<String>>,
    case_sensitive: bool,
    context_lines: usize,
    max_results: usize,
) -> PyResult<Vec<String>> {
    let root = Path::new(path);
    if !root.exists() {
        return Err(pyo3::exceptions::PyValueError::new_err(
            format!("Path '{}' does not exist.", path),
        ));
    }

    let pattern = if case_sensitive {
        Regex::new(query)
    } else {
        Regex::new(&format!("(?i){}", query))
    };

    let re = match pattern {
        Ok(r) => r,
        Err(e) => return Err(pyo3::exceptions::PyValueError::new_err(
            format!("Invalid regex: {}", e),
        )),
    };

    let exts: Option<Vec<String>> = file_extensions.map(|v| {
        v.into_iter().map(|e| e.trim_start_matches('.').to_lowercase()).collect()
    });

    // ── Phase 1: Collect files using the `ignore` crate (respects .gitignore) ──
    let files: Vec<_> = ignore::WalkBuilder::new(root)
        .hidden(true)
        .git_ignore(true)
        .git_global(true)
        .git_exclude(true)
        .filter_entry(|e| {
            let name = e.file_name().to_string_lossy();
            !should_ignore(&name)
        })
        .build()
        .filter_map(|e| e.ok())
        .filter(|e| e.file_type().map_or(false, |ft| ft.is_file()))
        .filter(|e| {
            if let Some(ref exts) = exts {
                e.path()
                    .extension()
                    .and_then(|ext| ext.to_str())
                    .map(|ext| exts.contains(&ext.to_lowercase()))
                    .unwrap_or(false)
            } else {
                true
            }
        })
        .collect();

    // ── Phase 2: Search files in parallel with Rayon ──
    let results = Mutex::new(Vec::<String>::new());

    files.par_iter().for_each(|entry| {
        // Early exit if we already have enough results
        {
            let r = results.lock().unwrap();
            if r.len() >= max_results {
                return;
            }
        }

        let content = match std::fs::read_to_string(entry.path()) {
            Ok(c) => c,
            Err(_) => return,
        };

        let lines: Vec<&str> = content.lines().collect();
        let mut local_results: Vec<String> = Vec::new();

        for (i, line) in lines.iter().enumerate() {
            if re.is_match(line) {
                let start = i.saturating_sub(context_lines);
                let end = (i + context_lines + 1).min(lines.len());
                for j in start..end {
                    local_results.push(format!(
                        "{}:{}:{}",
                        entry.path().display(),
                        j + 1,
                        lines[j]
                    ));
                }
            }
        }

        if !local_results.is_empty() {
            let mut r = results.lock().unwrap();
            let remaining = max_results.saturating_sub(r.len());
            r.extend(local_results.into_iter().take(remaining));
        }
    });

    Ok(results.into_inner().unwrap())
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(search_code, m)?)?;
    Ok(())
}
