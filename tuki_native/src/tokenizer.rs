use pyo3::prelude::*;

/// Estimates the number of tokens in a text string.
///
/// Uses content-aware heuristics:
///  - Code (high symbol ratio): ~3 chars/token
///  - Mixed content: ~3.5 chars/token
///  - Natural language: ~4 chars/token
///
/// This is much faster than calling tiktoken from Python and gives
/// a good-enough estimate for context window management.
#[pyfunction]
pub fn estimate_tokens(text: &str) -> usize {
    if text.is_empty() {
        return 0;
    }

    let total_chars = text.len();
    let non_alnum_count = text
        .chars()
        .filter(|c| !c.is_alphanumeric() && !c.is_whitespace())
        .count();

    let symbol_ratio = non_alnum_count as f64 / total_chars.max(1) as f64;

    let chars_per_token = if symbol_ratio > 0.25 {
        3.0 // code: lots of symbols
    } else if symbol_ratio > 0.10 {
        3.5 // mixed content
    } else {
        4.0 // natural language
    };

    (total_chars as f64 / chars_per_token).ceil() as usize
}

/// Estimates the total tokens across all messages in a conversation.
/// Expects a JSON array of message objects: [{"role": "...", "content": "..."}, ...]
#[pyfunction]
pub fn estimate_context_tokens(messages_json: &str) -> PyResult<usize> {
    // Simple approach: parse JSON and sum content token estimates
    // We avoid pulling in serde_json by doing lightweight parsing
    let mut total: usize = 0;

    // Each message has ~4 token overhead for role/formatting
    let message_count = messages_json.matches("\"role\"").count();
    total += message_count * 4;

    // Estimate based on total text size (excluding JSON structure)
    let content_chars: usize = messages_json.len();
    total += estimate_tokens(messages_json);

    Ok(total)
}

/// Truncates text intelligently for LLM context.
///
/// Keeps:
///  - First `head_lines` lines (usually contain important context)
///  - Last `tail_lines` lines (usually contain the result)
///  - Any lines containing "error", "warning", "failed" (case-insensitive)
///
/// Much smarter than a simple line-count truncation.
#[pyfunction]
#[pyo3(signature = (text, max_lines=50))]
pub fn smart_truncate(text: &str, max_lines: usize) -> String {
    if text.is_empty() {
        return String::new();
    }

    let lines: Vec<&str> = text.lines().collect();
    if lines.len() <= max_lines {
        return text.to_string();
    }

    let head_lines = max_lines / 3;           // ~33% from beginning
    let tail_lines = max_lines / 3;           // ~33% from end
    let important_budget = max_lines - head_lines - tail_lines; // ~33% for important lines

    let mut result: Vec<String> = Vec::with_capacity(max_lines + 3);

    // Head
    for line in lines.iter().take(head_lines) {
        result.push(line.to_string());
    }

    // Important lines from the middle
    let middle_start = head_lines;
    let middle_end = lines.len().saturating_sub(tail_lines);
    let middle = &lines[middle_start..middle_end];

    let mut important: Vec<(usize, &str)> = Vec::new();
    for (i, line) in middle.iter().enumerate() {
        let lower = line.to_lowercase();
        if lower.contains("error")
            || lower.contains("warning")
            || lower.contains("failed")
            || lower.contains("exception")
            || lower.contains("traceback")
            || lower.contains("panic")
        {
            important.push((middle_start + i, line));
        }
    }

    if !important.is_empty() {
        let take_count = important.len().min(important_budget);
        result.push(format!(
            "\n... [{} lines omitted — showing {} important lines] ...\n",
            middle.len(),
            take_count
        ));
        for (line_num, line) in important.iter().take(take_count) {
            result.push(format!("L{}: {}", line_num + 1, line));
        }
    } else {
        result.push(format!(
            "\n... [{} lines omitted] ...\n",
            middle.len()
        ));
    }

    // Tail
    for line in lines.iter().skip(lines.len() - tail_lines) {
        result.push(line.to_string());
    }

    result.join("\n")
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(estimate_tokens, m)?)?;
    m.add_function(wrap_pyfunction!(estimate_context_tokens, m)?)?;
    m.add_function(wrap_pyfunction!(smart_truncate, m)?)?;
    Ok(())
}
