# pytransitions core reuse

Novel vendors the complete, unmodified core module with its package initializer and version file from [pytransitions/transitions](https://github.com/pytransitions/transitions), commit `bd42b38f3627e6bca7274fb4d9af2e105f75da7c`, version 0.9.4. Observed 6,595 stars on 2026-10-01. The original MIT license is preserved in `LICENSE`; exact upstream/local Git blob identities are recorded in `provenance.json`.

Files copied verbatim: `transitions/core.py`, `transitions/__init__.py`, `transitions/version.py`. No changes were made to those upstream files. Only the core needed for the writer's fixed phase transitions is included; optional diagrams, async/nested extensions and upstream test frameworks are not pulled into Novel. The existing `six` dependency is explicitly declared.

Novel-owned code defines the writing phases, version guards, explicit caller-provided author decisions and persistence/context rules around `Machine`. It uses `auto_transitions=False`; untrusted JSON cannot supply arbitrary callbacks or import paths. This is an actual state-flow execution path when a Python executor is available, not a claim that a GitHub file plugin runs Python.

The state machine does not authenticate a human author and does not make independent literary-quality decisions. GPT must verify the actual author's instruction before submitting a confirmation event. State validation, legal transitions and local synthetic replay do not constitute author acceptance, whole-novel quality or a multi-file/Drive transaction guarantee.
