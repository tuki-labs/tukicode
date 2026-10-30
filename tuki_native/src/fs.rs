use pyo3::prelude::*;
use std::path::Path;
use walkdir::WalkDir;

use crate::DEFAULT_IGNORE;

fn should_ignore(name: &str, extra_ignore: &[String]) -> bool {
    DEFAULT_IGNORE.contains(&name) || extra_ignore.iter().any(|i| i == name)
}

/// Returns a directory tree string, ignoring common heavy directories.
/// Uses the `ignore` crate to respect .gitignore when available.
#[pyfunction]
#[pyo3(signature = (path, max_depth=4, ignore=None))]
pub fn get_project_tree(
    path: &str,
    max_depth: usize,
    ignore: Option<Vec<String>>,
) -> PyResult<String> {
    let root = Path::new(path);
    if !root.exists() || !root.is_dir() {
        return Err(pyo3::exceptions::PyValueError::new_err(
            format!("Directory '{}' does not exist.", path),
        ));
    }

    let extra_ignore = ignore.unwrap_or_default();
    let mut lines: Vec<String> = Vec::new();
    let root_name = root.file_name()
        .and_then(|n| n.to_str())
        .unwrap_or(path);
    lines.push(format!("{}/", root_name));

    build_tree(root, "", 0, max_depth, &extra_ignore, &mut lines);
    Ok(lines.join("\n"))
}

fn build_tree(
    dir: &Path,
    prefix: &str,
    depth: usize,
    max_depth: usize,
    extra_ignore: &[String],
    lines: &mut Vec<String>,
) {
    if depth > max_depth {
        return;
    }

    let mut entries: Vec<_> = match std::fs::read_dir(dir) {
        Ok(rd) => rd
            .filter_map(|e| e.ok())
            .filter(|e| {
                let name = e.file_name();
                let name_str = name.to_string_lossy();
                !should_ignore(&name_str, extra_ignore)
            })
            .collect(),
        Err(_) => {
            lines.push(format!("{}└── [Permission denied]", prefix));
            return;
        }
    };

    if entries.len() > 100 {
        lines.push(format!(
            "{}└── [Too many items ({}), use a more specific path]",
            prefix,
            entries.len()
        ));
        return;
    }

    // Dirs first, then files — both sorted alphabetically
    entries.sort_by(|a, b| {
        let a_is_dir = a.path().is_dir();
        let b_is_dir = b.path().is_dir();
        b_is_dir.cmp(&a_is_dir)
            .then_with(|| a.file_name().to_string_lossy().to_lowercase()
                .cmp(&b.file_name().to_string_lossy().to_lowercase()))
    });

    let count = entries.len();
    for (i, entry) in entries.iter().enumerate() {
        let is_last = i == count - 1;
        let connector = if is_last { "└── " } else { "├── " };
        let name = entry.file_name().to_string_lossy().into_owned();
        lines.push(format!("{}{}{}", prefix, connector, name));

        if entry.path().is_dir() {
            let extension = if is_last { "    " } else { "│   " };
            build_tree(
                &entry.path(),
                &format!("{}{}", prefix, extension),
                depth + 1,
                max_depth,
                extra_ignore,
                lines,
            );
        }
    }
}

/// Finds files matching a glob-style pattern under `root`.
/// Uses the `ignore` crate for .gitignore-aware walking.
#[pyfunction]
#[pyo3(signature = (pattern, root, max_depth=5, ignore=None))]
pub fn find_files(
    pattern: &str,
    root: &str,
    max_depth: usize,
    ignore: Option<Vec<String>>,
) -> PyResult<Vec<String>> {
    let root_path = Path::new(root);
    if !root_path.exists() {
        return Err(pyo3::exceptions::PyValueError::new_err(
            format!("Root '{}' does not exist.", root),
        ));
    }

    let extra_ignore = ignore.unwrap_or_default();
    let pattern_lower = pattern.to_lowercase().replace('*', "");
    let mut results: Vec<String> = Vec::new();

    for entry in ignore::WalkBuilder::new(root_path)
        .max_depth(Some(max_depth))
        .hidden(true)
        .git_ignore(true)
        .git_global(true)
        .filter_entry(move |e| {
            let name = e.file_name().to_string_lossy();
            !DEFAULT_IGNORE.contains(&name.as_ref())
                && !extra_ignore.iter().any(|i| i == name.as_ref())
        })
        .build()
        .filter_map(|e| e.ok())
    {
        if entry.file_type().map_or(false, |ft| ft.is_file()) {
            let name = entry.file_name().to_string_lossy().to_lowercase();
            if pattern_lower.is_empty() || name.contains(&pattern_lower) {
                results.push(entry.path().to_string_lossy().into_owned());
            }
            if results.len() >= 100 {
                break;
            }
        }
    }

    Ok(results)
}

/// Lists the contents of a directory (non-recursive by default).
#[pyfunction]
#[pyo3(signature = (path, recursive=false, show_hidden=false))]
pub fn list_dir(
    path: &str,
    recursive: bool,
    show_hidden: bool,
) -> PyResult<String> {
    let p = Path::new(path);
    if !p.exists() || !p.is_dir() {
        return Err(pyo3::exceptions::PyValueError::new_err(
            format!("Directory '{}' does not exist.", path),
        ));
    }

    let mut lines: Vec<String> = Vec::new();
    let walker = WalkDir::new(p).max_depth(if recursive { 99 } else { 1 });

    for entry in walker.into_iter().filter_map(|e| e.ok()).skip(1) {
        let name = entry.file_name().to_string_lossy();
        if !show_hidden && name.starts_with('.') {
            continue;
        }
        if let Ok(meta) = entry.metadata() {
            let kind = if meta.is_dir() { "DIR " } else { "FILE" };
            let size: String = if meta.is_file() {
                meta.len().to_string()
            } else {
                "-".to_string()
            };
            let rel_path = entry.path().strip_prefix(p)
                .map(|r| r.to_string_lossy().into_owned())
                .unwrap_or_else(|_| name.to_string());
            lines.push(format!("{}\t{}\t{}", kind, size, rel_path));
        }
        if lines.len() > 200 {
            lines.push("... (truncated)".to_string());
            break;
        }
    }

    Ok(if lines.is_empty() {
        "Empty directory.".to_string()
    } else {
        lines.join("\n")
    })
}

/// Reads a file with partial line support.
/// Returns (content, total_lines). Only reads from start_line to start_line + max_lines.
/// Detects binary files and returns an error message instead.
#[pyfunction]
#[pyo3(signature = (path, max_lines=1000, start_line=0))]
pub fn read_file_lines(
    path: &str,
    max_lines: usize,
    start_line: usize,
) -> PyResult<(String, usize)> {
    let p = Path::new(path);
    if !p.exists() || !p.is_file() {
        return Err(pyo3::exceptions::PyValueError::new_err(
            format!("File '{}' does not exist or is not a file.", path),
        ));
    }

    // Quick binary check: read first 8KB
    let raw_start = match std::fs::read(p) {
        Ok(data) => data,
        Err(e) => return Err(pyo3::exceptions::PyIOError::new_err(
            format!("Error reading file: {}", e),
        )),
    };

    let check_len = raw_start.len().min(8192);
    let null_count = raw_start[..check_len].iter().filter(|&&b| b == 0).count();
    if null_count > check_len / 20 {
        return Err(pyo3::exceptions::PyValueError::new_err(
            "File appears to be binary. Cannot read as text.",
        ));
    }

    // Read as text
    let content = String::from_utf8_lossy(&raw_start);
    let all_lines: Vec<&str> = content.lines().collect();
    let total_lines = all_lines.len();

    if start_line >= total_lines {
        return Ok(("".to_string(), total_lines));
    }

    let end = (start_line + max_lines).min(total_lines);
    let selected: Vec<&str> = all_lines[start_line..end].to_vec();

    let mut result = String::new();
    for (i, line) in selected.iter().enumerate() {
        let line_num = start_line + i + 1;
        result.push_str(&format!("{:>4} | {}\n", line_num, line));
    }

    if end < total_lines {
        result.push_str(&format!(
            "\n... ({} more lines not shown. Use start_line={} to continue.)\n",
            total_lines - end,
            end
        ));
    }

    Ok((result, total_lines))
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(get_project_tree, m)?)?;
    m.add_function(wrap_pyfunction!(find_files, m)?)?;
    m.add_function(wrap_pyfunction!(list_dir, m)?)?;
    m.add_function(wrap_pyfunction!(read_file_lines, m)?)?;
    Ok(())
}
