use pyo3::prelude::*;
use regex::Regex;
use std::path::Path;
use walkdir::WalkDir;

const DEFAULT_IGNORE: &[&str] = &[
    "node_modules", ".git", "__pycache__", "venv", ".venv",
    "dist", "build", "target", ".expo", ".next", "out",
];

fn should_ignore(name: &str) -> bool {
    DEFAULT_IGNORE.contains(&name)
}

/// Searches for a pattern in files under `path`. Uses parallel file walking.
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

    let mut results: Vec<String> = Vec::new();

    for entry in WalkDir::new(root)
        .into_iter()
        .filter_entry(|e| !should_ignore(&e.file_name().to_string_lossy()))
        .filter_map(|e| e.ok())
    {
        if results.len() >= max_results {
            break;
        }
        if !entry.file_type().is_file() {
            continue;
        }

        // Extension filter
        if let Some(ref exts) = exts {
            let file_ext = entry.path()
                .extension()
                .and_then(|e| e.to_str())
                .map(|e| e.to_lowercase())
                .unwrap_or_default();
            if !exts.contains(&file_ext) {
                continue;
            }
        }

        let content = match std::fs::read_to_string(entry.path()) {
            Ok(c) => c,
            Err(_) => continue,
        };

        let lines: Vec<&str> = content.lines().collect();
        for (i, line) in lines.iter().enumerate() {
            if re.is_match(line) {
                let start = i.saturating_sub(context_lines);
                let end = (i + context_lines + 1).min(lines.len());
                for j in start..end {
                    results.push(format!(
                        "{}:{}:{}",
                        entry.path().display(),
                        j + 1,
                        lines[j]
                    ));
                }
                if results.len() >= max_results {
                    break;
                }
            }
        }
    }

    Ok(results)
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(search_code, m)?)?;
    Ok(())
}
