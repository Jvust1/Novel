# OpenWrite Integration

Novel selectively vendors three permissively licensed writing systems and keeps one AGPL system reference-only.

The main production adaptation is `novel_ai/quality_gate.py`, inspired by Open-Write's deterministic completion philosophy: real bytes, hashes and located review evidence outrank a model claiming that work is complete. The Novel version is Chinese-aware and intentionally narrower than literary grading.

Vendored upstream source remains under `third_party/openwrite/` with its original license. Do not silently copy AGPL code from `ilrein/openwrite` into Novel.

The quality gate is a backstop, not an automatic judge of literary merit. Repeated sentences are advisory because callbacks/refrains can be deliberate; independent human/model review remains separate.
