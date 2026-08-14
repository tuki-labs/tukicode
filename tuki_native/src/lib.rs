use pyo3::prelude::*;

mod fs;
mod search;
mod pty;
mod diff;
mod tokenizer;

// ── Shared constants ────────────────────────────────────────────────────────
// Single source of truth for default ignore patterns, used by fs.rs and search.rs.
pub const DEFAULT_IGNORE: &[&str] = &[
    "node_modules", ".git", "__pycache__", "venv", ".venv",
    "dist", "build", "target", ".expo", ".next", "out",
    "android", "ios", "Pods", ".pytest_cache",
    "tukicode.egg-info", ".tox", ".mypy_cache",
];

/// Returns the default ignore list so Python code can stay in sync.
#[pyfunction]
fn default_ignore_list() -> Vec<&'static str> {
    DEFAULT_IGNORE.to_vec()
}

/// tuki_native — Native Rust extension for TukiCode.
///
/// Provides high-performance replacements for:
///   - fs:        get_project_tree, find_files, list_dir, read_file_lines
///   - search:    search_code (parallel via Rayon, .gitignore-aware)
///   - pty:       strip_control_sequences, strip_ansi, truncate_output
///   - diff:      apply_patch, compute_diff
///   - tokenizer: estimate_tokens, estimate_context_tokens, smart_truncate
#[pymodule]
fn tuki_native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // Version constant accessible from Python
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;

    // Shared constants
    m.add_function(wrap_pyfunction!(default_ignore_list, m)?)?;

    // Register all sub-modules
    fs::register(m)?;
    search::register(m)?;
    pty::register(m)?;
    diff::register(m)?;
    tokenizer::register(m)?;

    Ok(())
}
