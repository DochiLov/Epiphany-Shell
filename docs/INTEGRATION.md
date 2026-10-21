# ChatGPT / Codex / local observer handoff

## Status and purpose

This branch implements an **offline, reviewed data handoff**, not a remote-control
bridge, automatic GitHub poller, trading service, or continuous orchestrator.
It adds a common working agreement (`AGENTS.md`), a strict observer-health packet,
freshness assessment, and an optional adapter into the existing trace ledger.
No private conversation transcript or proprietary cognitive specification is
published here.

The intended division of work is:

| Component | Responsibility in this iteration | What is not implied |
| --- | --- | --- |
| ChatGPT / Epiphany | Review connected GitHub changes and permissioned reports; compare observations and interpretations | Direct invocation of another Codex session or a laptop shell |
| Codex Cloud | Inspect this revision and run offline tests; review incoming normalized reports | Access to a laptop's files, processes, sessions, or credentials |
| Existing local Codex session | Inspect the already-installed observer with read-only methods; produce a normalized report | Permission to repair, deploy, trade, or restart |
| Drift Signal observer | Its existing local collection behavior and journal | An order gateway or a model-reasoning loop added by this patch |
| OpenClaw | A possible later producer/consumer of the same packet contract | Installed configuration, an activated gateway, or an audited runtime adapter |
| GitHub | Reviewed source, public-safe technical continuity, and pull-request review | A private telemetry store, automatic command bus, or shared execution memory |

Official Codex documentation describes repository-level `AGENTS.md` guidance,
separate cloud task working files, and cloud/local execution choices. The common
repository is useful shared context; it does not by itself connect those running
environments. See the dated source references below.

## What the implementation does

`epiphany_trace/handoff.py` uses only the Python standard library. It reads one
explicitly provided normalized JSON packet, never a credential directory or the
live observer's SQLite journal. Unknown fields, free-form producer names,
noncanonical report IDs, duplicate JSON keys, naive/invalid/future timestamps,
and malformed evidence are rejected. Input reads are limited to 16 KiB.

Only fixed enumerations, timestamps, a UUID, a failure count, and a stop flag are
accepted. There is no command, URL, filename, host identifier, financial value,
or raw-log field. This reduces accidental disclosure; it is **not** a universal
secret detector, proof of authenticity, or permission to publish a real report.

A packet's `observed_at` is the time the producer completed its evidence reading.
`heartbeat_at` and `last_collection_at` retain their original source timestamps.
The consumer adds its own `received_at`. Freshness uses that receiving clock, so
repackaging an old heartbeat does not make it fresh. Future timestamps fail
validation rather than silently receiving a healthy interpretation.

The default 300-second freshness budget is a configurable diagnostic reference,
not an uptime guarantee or a verified collector service-level requirement.
Collection age is displayed without declaring failure merely because a market
window is closed. This patch does not implement an exchange calendar.

Assessment flags describe **reported** states and staleness. Even an empty flag
list means only that the packet reports no selected issues; there is deliberately
no `healthy: true` or authenticated-source result.

## Packet contract

Use `examples/observer_health.synthetic.json` as the schema example, not as live
evidence. It contains an intentionally historical fictitious observation.

| Field | Required meaning |
| --- | --- |
| `schema` | Exactly `epiphany.observer-health.v1` |
| `report_id` | Canonical lowercase UUID created for this observation; preserve it on relay |
| `producer` | `chatgpt`, `codex-cloud`, `codex-local`, `openclaw`, or `drift-observer`; identifies the declared original producer, not the forwarder |
| `subject` | Exactly `drift-signal-observer`; private host mappings remain outside the public repo |
| `observed_at` | Source observation time with seconds and explicit timezone |
| `evidence.process_state` | `running`, `stopped`, or `unknown`; verify process identity before claiming running |
| `evidence.task_state` | `running`, `ready`, `disabled`, or `unknown` |
| `evidence.phase` | `collecting`, `waiting_for_clock_window`, `bounded_collection_complete`, `stopped`, `error`, or `unknown` |
| `evidence.heartbeat_at` | Original heartbeat timestamp, or null |
| `evidence.last_collection_at` | Original timestamp of the reported collection outcome, or null |
| `evidence.last_collection_result` | `success`, `failure`, or `unknown`; success/failure requires a collection timestamp |
| `evidence.consecutive_failures` | Integer 0 through 1,000,000, or null when unavailable; booleans are not counts |
| `evidence.stop_requested` | Boolean, or null when unavailable |

All fields are required; unavailable values use the explicit `unknown`/null forms.
Do not silently map an unfamiliar phase to success. Do not infer a successful
broker collection from process existence or a recent heartbeat alone.

## Run and verify

From an isolated checkout of the integration branch, with Python 3.11+:

```sh
python -m unittest discover -s tests -v
python -m epiphany_trace.handoff examples/observer_health.synthetic.json
```

No dependencies, network access, model API key, broker account, or installation of
OpenClaw are needed. The example should report staleness relative to the actual
receiving clock. Do not change its timestamp and call it live evidence.

For a genuinely observed, reviewed packet kept **outside Git tracking**:

```sh
python -m epiphany_trace.handoff .local/observer-health.json
python -m epiphany_trace.handoff .local/observer-health.json --save
```

The first command does not write a ledger. `--save` writes a separate checkout-local
`.local/epiphany_handoff.sqlite3`. It refuses a symlink for that directory/file and
an existing database without the expected trace tables. It does not write the
observer journal. Use a single writer; concurrent imports are not an acceptance
claim of this prototype.

Exit status **0** means the packet was assessed (and saved if requested), even
when stale/error/unknown flags exist. Status **2** means validation or local I/O
failed. Callers must inspect flags rather than treating exit 0 as observer health.
The CLI does not print raw exceptions that might disclose packet contents or paths.

### Trace behavior

`import_report(store, packet, received_at=..., parent_ids=...)` maps the normalized
packet to an `observation` in the existing `TraceStore`. Exact replay returns the
same record without adding another. Reusing an ID with altered content or ancestry
fails without replacing the original. Optional parent links preserve temporal
lineage; the base ledger enforces missing-parent and chronology constraints.

The content digest is a stable packet identifier, **not a signature or evidence
of independent sources**. Forwarders preserve the packet and its producer/ID/time.
A new receiver does not create a new independent observation. Receipt assessments
are returned separately; the source record retains its source time. Capture the
assessment privately when a durable receipt audit is required.

Interpretations belong in separate `inference` or `revision` records referencing
those observations. The existing trace prototype is not the full private A143,
A700, Mobius, or Sigma-T system, and this patch does not claim to implement it.

## Next execution: existing local Codex session

Use the already-open health-check session rather than creating another remote
connection or cloud environment. The following is the continuation instruction:

> Read AGENTS.md and docs/CONTINUATION_2026-10-21.md from the integration branch of
> DochiLov/Epiphany-Shell. Use an isolated checkout, not the running observer's
> installation directory. Run the synthetic tests first. In the already-connected
> local environment, inspect the existing Drift Signal installation read-only.
> Verify current host time, scheduled-task state, process identity/liveness, the
> saved status heartbeat, latest actual collection outcome, failures, and stop
> state. Inspect any status helper before executing it and use it only if its path
> is read-only; do not invoke setup/start/resume/repair helpers. Use read-only access
> for the observer journal if needed and do not change its journal mode. Never
> read credential stores or include raw logs/account details in the response.
> Build a fresh normalized health packet from verified fields; use unknown/null
> where evidence is missing. Keep host identifiers and paths private. Validate the
> packet with epiphany_trace.handoff. Return the timestamped assessment and the
> reviewed packet through the existing private session, not a public GitHub commit
> or issue. Do not modify tasks, code, permissions, processes, or trading state.

A local agent must determine the actual installed status format. This patch does
**not** implement or test a raw v0.7.1 status-file parser, Windows process inspector,
or automatic export from the deployed observer. Those are deliberately separate
from the normalized receiver.

## Acceptance gates still open

1. The existing local session produces a fresh normalized packet tied to actual
   process and collection evidence. A device-online screenshot is insufficient.
2. A receiver imports that same reviewed packet and retains original identity,
   timestamps, source declaration, and unknowns.
3. A later observation links to the earlier one and permits a real prospective
   interpretation/outcome comparison, without rewriting the earlier record.
4. Any continuous private transport, authenticated producer identity, OpenClaw
   adapter, or deployment is designed and authorized separately. No GitHub Actions
   polling, remote shell bridge, automatic issue execution, or trading path is
   introduced here.

## Primary references consulted 2026-10-21

- Repository instructions: https://developers.openai.com/codex/agent-configuration/agents-md
- Cloud environments: https://developers.openai.com/codex/environments/cloud-environments
- Environment boundaries: https://developers.openai.com/codex/environments/modes
- Remote connections: https://developers.openai.com/codex/remote-connections

These document product behavior; they do not prove the state of any particular
account, connection, host, task, or deployment.
