use pyo3::prelude::*;
use regex::Regex;
use std::sync::OnceLock;

// ── Pre-compiled regex patterns (compiled once, reused on every call) ──────────

static RE_CURSOR_POS: OnceLock<Regex> = OnceLock::new();
static RE_CURSOR_MOVE: OnceLock<Regex> = OnceLock::new();
static RE_ERASE: OnceLock<Regex> = OnceLock::new();
static RE_MODE: OnceLock<Regex> = OnceLock::new();
static RE_MOUSE: OnceLock<Regex> = OnceLock::new();
static RE_KEYPAD: OnceLock<Regex> = OnceLock::new();
static RE_OSC_BELL: OnceLock<Regex> = OnceLock::new();
static RE_OSC_ST: OnceLock<Regex> = OnceLock::new();
static RE_CTRL: OnceLock<Regex> = OnceLock::new();
static RE_CRLF: OnceLock<Regex> = OnceLock::new();
static RE_CR: OnceLock<Regex> = OnceLock::new();
static RE_ALL_ANSI: OnceLock<Regex> = OnceLock::new();

fn re_cursor_pos() -> &'static Regex {
    RE_CURSOR_POS.get_or_init(|| Regex::new(r"\x1b\[\d*;\d*[Hf]").unwrap())
}
fn re_cursor_move() -> &'static Regex {
    RE_CURSOR_MOVE.get_or_init(|| Regex::new(r"\x1b\[\d*[ABCD]").unwrap())
}
fn re_erase() -> &'static Regex {
    RE_ERASE.get_or_init(|| Regex::new(r"\x1b\[\d*[JK]").unwrap())
}
fn re_mode() -> &'static Regex {
    RE_MODE.get_or_init(|| Regex::new(r"\x1b\[\?\d+[hl]").unwrap())
}
fn re_mouse() -> &'static Regex {
    RE_MOUSE.get_or_init(|| Regex::new(r"\x1b\[[\d;]*[Mm]").unwrap())
}
fn re_keypad() -> &'static Regex {
    RE_KEYPAD.get_or_init(|| Regex::new(r"\x1b[=>]").unwrap())
}
fn re_osc_bell() -> &'static Regex {
    RE_OSC_BELL.get_or_init(|| Regex::new(r"\x1b\]0;[^\x07]*\x07").unwrap())
}
fn re_osc_st() -> &'static Regex {
    RE_OSC_ST.get_or_init(|| Regex::new(r"\x1b\]0;.*?\\").unwrap())
}
fn re_ctrl() -> &'static Regex {
    RE_CTRL.get_or_init(|| Regex::new(r"[\x00-\x08\x0b\x0c\x0e-\x1a\x1c-\x1f]").unwrap())
}
fn re_crlf() -> &'static Regex {
    RE_CRLF.get_or_init(|| Regex::new(r"\r\n").unwrap())
}
fn re_cr() -> &'static Regex {
    RE_CR.get_or_init(|| Regex::new(r"\r").unwrap())
}
fn re_all_ansi() -> &'static Regex {
    RE_ALL_ANSI.get_or_init(|| {
        Regex::new(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])").unwrap()
    })
}

// ── Public functions ────────────────────────────────────────────────────────────

/// Removes cursor-movement control sequences but preserves ANSI color codes.
/// Used for terminal output that needs colors (QR codes, etc.).
#[pyfunction]
pub fn strip_control_sequences(text: &str) -> String {
    let s = re_cursor_pos().replace_all(text, "");
    let s = re_cursor_move().replace_all(&s, "");
    let s = re_erase().replace_all(&s, "");
    let s = re_mode().replace_all(&s, "");
    let s = re_mouse().replace_all(&s, "");
    let s = re_keypad().replace_all(&s, "");
    let s = re_osc_bell().replace_all(&s, "");
    let s = re_osc_st().replace_all(&s, "");
    let s = re_ctrl().replace_all(&s, "");
    let s = re_crlf().replace_all(&s, "\n");
    let s = re_cr().replace_all(&s, "\n");
    s.into_owned()
}

/// Removes ALL ANSI codes including colors. Use for plain-text output.
#[pyfunction]
pub fn strip_ansi(text: &str) -> String {
    re_all_ansi().replace_all(text, "").into_owned()
}

/// Strips control sequences and truncates to `max_lines` (keeping the last N lines).
#[pyfunction]
#[pyo3(signature = (text, max_lines=500))]
pub fn truncate_output(text: &str, max_lines: usize) -> String {
    if text.is_empty() {
        return String::new();
    }
    let cleaned = strip_control_sequences(text);
    let lines: Vec<&str> = cleaned.lines().collect();
    if lines.len() <= max_lines {
        return cleaned;
    }
    let skipped = lines.len() - max_lines;
    format!(
        "... [Truncated first {} lines] ...\n{}",
        skipped,
        lines[skipped..].join("\n")
    )
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(strip_control_sequences, m)?)?;
    m.add_function(wrap_pyfunction!(strip_ansi, m)?)?;
    m.add_function(wrap_pyfunction!(truncate_output, m)?)?;
    Ok(())
}
