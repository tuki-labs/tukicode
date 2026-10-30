use pyo3::prelude::*;
use similar::TextDiff;
use std::path::Path;

/// Applies a text replacement to a file.
/// `occurrence`:
///   -1 → replace ALL occurrences
///    0 → replace a unique occurrence (reject ambiguity)
///    N → replace the N-th occurrence (0-indexed)
///
/// Returns a unified diff string on success.
#[pyfunction]
#[pyo3(signature = (path, old_str, new_str, occurrence=0))]
pub fn apply_patch(
    path: &str,
    old_str: &str,
    new_str: &str,
    occurrence: i32,
) -> PyResult<String> {
    let p = Path::new(path);
    if !p.exists() || !p.is_file() {
        return Err(pyo3::exceptions::PyValueError::new_err(
            format!("File '{}' does not exist.", path),
        ));
    }

    let content = std::fs::read_to_string(p).map_err(|e| {
        pyo3::exceptions::PyIOError::new_err(format!("Error reading file: {}", e))
    })?;

    if old_str.is_empty() || occurrence < -1 {
        return Err(pyo3::exceptions::PyValueError::new_err("Invalid patch target or occurrence."));
    }
    let count = content.matches(old_str).count();
    if occurrence == 0 && count > 1 {
        return Err(pyo3::exceptions::PyValueError::new_err("Ambiguity: old_str matches multiple locations."));
    }
    if count == 0 {
        return Err(pyo3::exceptions::PyValueError::new_err(
            "The target string was not found in the file.",
        ));
    }

    let new_content = if occurrence == -1 {
        // Replace all occurrences
        content.replace(old_str, new_str)
    } else if occurrence == 0 {
        // Replace first occurrence
        content.replacen(old_str, new_str, 1)
    } else {
        // Replace N-th occurrence
        let nth = occurrence as usize;
        if nth >= count {
            return Err(pyo3::exceptions::PyValueError::new_err(
                format!(
                    "Requested occurrence {} but only {} found.",
                    nth, count
                ),
            ));
        }
        let mut result = String::with_capacity(content.len());
        let mut found = 0;
        let mut last_end = 0;

        for (start, _) in content.match_indices(old_str) {
            if found == nth {
                result.push_str(&content[last_end..start]);
                result.push_str(new_str);
                last_end = start + old_str.len();
                // Continue to append the rest
                result.push_str(&content[last_end..]);
                break;
            } else {
                found += 1;
            }
        }
        if result.is_empty() {
            content.clone()
        } else {
            result
        }
    };

    // Write the modified content
    std::fs::write(p, &new_content).map_err(|e| {
        pyo3::exceptions::PyIOError::new_err(format!("Error writing file: {}", e))
    })?;

    // Generate unified diff
    let diff = compute_diff_internal(&content, &new_content, path);
    Ok(diff)
}

/// Computes a unified diff between two text strings.
#[pyfunction]
pub fn compute_diff(old_content: &str, new_content: &str, filename: &str) -> String {
    compute_diff_internal(old_content, new_content, filename)
}

fn compute_diff_internal(old: &str, new: &str, filename: &str) -> String {
    let diff = TextDiff::from_lines(old, new);
    let mut result = String::new();

    result.push_str(&format!("--- a/{}\n", filename));
    result.push_str(&format!("+++ b/{}\n", filename));

    for hunk in diff.unified_diff().context_radius(3).iter_hunks() {
        result.push_str(&format!("{}", hunk));
    }

    result
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(apply_patch, m)?)?;
    m.add_function(wrap_pyfunction!(compute_diff, m)?)?;
    Ok(())
}
