use pyo3::prelude::*;

mod fs;
mod search;
mod pty;

/// tuki_native — Native Rust extension for TukiCode.
///
/// Provides high-performance replacements for:
///   - fs:     get_project_tree, find_files, list_dir
///   - search: search_code
///   - pty:    strip_control_sequences, strip_ansi, truncate_output
#[pymodule]
fn tuki_native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // Version constant accessible from Python
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;

    // Register all functions into the flat module namespace
    fs::register(m)?;
    search::register(m)?;
    pty::register(m)?;

    Ok(())
}
