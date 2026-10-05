# qdrant-client provenance

- Upstream: https://github.com/qdrant/qdrant-client
- Version: v1.19.1
- Pinned commit: cf747f4b6fa71ba35dfb467931f3fa65f2cdf263
- License: Apache-2.0 (upstream LICENSE at the pinned commit)
- Source selected from: GitHub
- Local use: optional client dependency behind Novel's existing RecallBackend contract.
- Local modifications: no upstream Python source is vendored. Novel adds its own adapter over the public qdrant-client API, with stable point identity, fail-closed vector/payload validation, and local-only factory defaults.
- Content boundary: raw reference novels are not automatically indexed.

Because no upstream source file is copied into this repository, the upstream package license is recorded by identifier and pinned source URL rather than duplicated as vendored code.
