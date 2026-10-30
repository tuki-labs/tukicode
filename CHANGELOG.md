# Changelog

## 1.3.4 — 2026-10-30

- Guide first-time users through setup; incomplete setup is requested again.
- Link directly to OpenRouter API key creation and fetch coding recommendations
  with native tool support, prices, context sizes and free alternatives.
- Verify OpenRouter credentials, model access and an actual synthetic tool call
  before saving a selection and before opening an OpenRouter chat session.
  The probe never executes tools or sends project files; normal model charges
  and free-tier quotas apply.
- Keep the previous configuration when validation or saving fails, and guide
  users away from rejected models. Show actionable, redacted provider errors.
- Separate risk limits from approval frequency. Preserve Anthropic tool results
  and the correct types and optional arguments in tool schemas.
- Require tool evidence and a separate model review before completing Plan/Build
  steps. Stop dependent work on unverified steps and avoid retrying side effects.
  Step review is an additional model call, not a proof of correctness.
- Report real shell exit codes, including failed background commands, and keep
  stop/resume state consistent without starting concurrent operations.
- Save TOML atomically with correct escaping and retain all provider settings.
  Use writable user configuration paths for new installed copies.
- Reject ambiguous file patches consistently in Python and Rust.
- Fix the native Rust build, package controllers/integrations/prompts and runtime
  dependencies, and build the native extension before packaging release binaries.
- Restore the last submitted message with Ctrl+Up without sending it.
- Add regression workflows and tests. Tool calls remain sequential; Rust code
  search runs in parallel.
