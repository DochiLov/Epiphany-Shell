# Epiphany Shell — trace prototype

An intentionally small, **public-safe experimental scaffold** for preserving how observations, inferences, and revisions relate across time. No personal conversation archives or proprietary system definitions are included.

## What exists in this branch

- Immutable, actor-attributed records stored in SQLite.
- Explicit provenance for observations and parent references for derived statements.
- Backward and forward traversal through an append-only dependency graph.
- Deduplication of *declared* source references, preventing repeated retellings of a single source from counting as independent evidence.
- Deterministic local unit tests, using synthetic data only.

Run with Python 3.11+:

```bash
python -m unittest discover -s tests -v
```

## What it does **not** establish

This is **not** the full A700, A143, Möbius, or Sigma-T architecture. It neither has access to ChatGPT's historical records nor establishes that a model is self-aware, autonomously learning, or causally reconstructing its own hidden processes. `source_ref` is a caller-provided attribution, not authenticated evidence. An independent source-checking layer, contradiction evaluation, access controls, audit immutability, and adversarial testing would be needed before any stronger claim.

The older `epiphany-wrapper_v0.1.0.zip` on its historical branch is not modified. The `main` branch is left untouched pending review of this experimental pull request.

## Proposed next gates

1. Review the original private specifications and map only verified behavior into explicit contracts.
2. Build evidence-integrity checks and controlled disagreement/correction tests.
3. Test chronological retrieval on genuinely held-out, permissioned records, with source fidelity and forward/backward coverage metrics.
4. Only then compare a model-driven consumer with deterministic baselines.