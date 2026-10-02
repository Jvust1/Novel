# Ruff development tool provenance

Novel runs the official Ruff CLI as a pinned development dependency (`ruff==0.16.9`); it does not copy Ruff runtime source into the application or enable a new fiction workflow framework.

- Repository: https://github.com/astral-sh/ruff
- Verified 2026-10-01 17:56 UTC: 49,870 stars, MIT
- Exact release: 0.16.9, commit `0be08a206f9c3180afd3e93bcc792ed5cb1f4db1`
- Complete upstream LICENSE, including its embedded derived-work notices, retained verbatim in `LICENSE`
- Upstream LICENSE Git blob: `655a0c76fc5539b2f8e63b673741a5fd0e0c5799`
- Local LICENSE SHA-256: `2597d854122b77ddc71971564ca2350a37608575ce324adc5650a2b2051c8f18`
- License source: https://github.com/astral-sh/ruff/blob/0be08a206f9c3180afd3e93bcc792ed5cb1f4db1/LICENSE

Actual integration is the required CI `ruff check app.py novel_ai scripts tests --select E9,F63,F7,F82` command and a separate advisory default diagnostic report. The fatal command has no exit-zero or continue-on-error. Default diagnostics are explicitly advisory; their count is not represented as a full static-clean result. Core application and transitive dependencies remain range-constrained rather than hash-locked.

The CI gate recipe and `scripts/check_integrations.py` root bootstrap are reused from this repository's PR #60, exact head `bc87ef1f87c2d789a44e9364f65e095e360a0cf1`. Original CI blob `898347cefa8c43fab47c0eea1ea34c65eff114b5`; original probe blob `a7dd01a877e2285abc441b80f9c98e7a44e90498`. The CI adds one current-public-entry validation step here; the probe file is retained byte-for-byte. No #55/#58/#59 feature code is incorporated by this reuse.
