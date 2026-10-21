# Validation record — 2026-10-21

## Actually executed

- Environment: isolated Linux workspace, Python 3.13.5; not the local laptop or Codex Cloud.
- Completed at: 2026-10-21T20:27:34.489634+00:00.
- Baseline: `03f776742b5e0fa1325f846d4b131f4acbbfbcbd`, original draft PR #2.
- The three baseline source/test files were obtained from the connected GitHub
  response and matched the repository Git blob hashes before execution. The
  original README text was also hash-checked before appending a navigation section.
- Baseline run: **11 tests passed**.
- Full run: `python -m unittest discover -s tests -v` — **47 tests passed**,
  consisting of 11 unchanged baseline tests and 36 new handoff tests. No skips.
- CLI smoke check: the historical synthetic example produced `report_stale` and
  `heartbeat_stale`, retained the original timestamp, and created no `.local`
  directory without `--save`.
- Save/replay, unknown-field rejection, future/overflow timestamps, conflict
  preservation, unrelated-database refusal, and symlink refusal were exercised
  with synthetic data in temporary directories.

## Source fingerprints

These are Git blob identities (SHA-1 over the Git blob header and file bytes), not
claims of authenticated telemetry. They allow comparing tested files with the
published tree. The three baseline files are unchanged.

| File | Git blob SHA |
| --- | --- |
| `epiphany_trace/__init__.py` | `ceb6bfa0b9b88d5707ba51a678db86e0a891e37a` |
| `epiphany_trace/graph.py` | `ad5548821fc6dd2c06ae2acb5e9b2515f3ade4c0` |
| `tests/test_graph.py` | `8696ae968a098d9bfc74b06d651d3e251bb0738f` |
| `epiphany_trace/handoff.py` | `bae45d294a3e122fdbded43859903afb27fcebe8` |
| `tests/test_handoff.py` | `89b5ca0b9c9ed9a83041d3da0af50a1403ba1277` |
| `examples/observer_health.synthetic.json` | `5725946c85a971c74017517db8c23a2116f97aa0` |

## Not executed or established

No Windows or live-host health check, raw observer status parser, live journal
read, broker query, model API call, OpenClaw runtime inspection, automatic
cross-session invocation, or deployment was performed. GitHub CI was not run as
part of this local validation. No test result establishes producer authenticity,
independent evidence, or the truth of a packet's claimed host state.

The default branch, original draft trace branch, historical wrapper branch,
laptop installation, scheduled tasks, broker state, and existing watches are not
modified by this proposal. Publication consists of a separate integration branch
and a draft pull request; it is not a merge or a deployment.
