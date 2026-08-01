# racing_edge — Architecture

The one-page map. For the betting method itself read `HANDICAPPING_METHOD.md`
and `docs/handicapping_notebook.md`; for how changes are allowed to happen read
`docs/IMPROVEMENT_PROTOCOL.md`. This file is the ENGINEERING contract — any
session (human or AI) touching the code reads this first.

## Core beliefs (never break these)

1. **The best horse wins the race — find the best horse.** Every lens is one
   jigsaw piece; no single signal decides a pick.
2. **Never invent facts.** Missing data prints as OWED. A blank is honest;
   a guess is corruption.
3. **The record judges everything.** Picks bank PRE-OFF in `data/nap.db` and
   settle against real results. No hindsight, no edits.
4. **Fail loudly.** A part that dies must say so — named exception, red line
   in health, crash email. Silent failure is the one unforgivable bug.
5. **Change by the ladder.** Every behavioural change carries a REVERT-IF, a
   measurement, and an escape hatch (`docs/IMPROVEMENT_PROTOCOL.md`).
6. **Lean.** Costs are real money. No speculative features, no agent fleets,
   no dependency creep.

## Module map (`src/racing_edge/`)

| Layer | Modules | Job |
|---|---|---|
| data | `client` `normalise` `evidence` | Racing API transport (Basic Auth, retry, tier-aware two-door horse_results), raw→domain parsing, per-runner evidence assembly (each fetch guarded → OWED) |
| domain | `models` `mark` `manner` `tells` `courses` | Pure form-reading: the mark (proven level, stale, up-in-grade), run style, in-running tells, course handedness |
| selection | `case` `conviction` | The jigsaw: family scoring, flags (cautions, not blindfolds), race gates |
| pipeline | `nap` `restudy` | Orchestration: read every readable handicap fair-and-even (`evaluate_field`), market shape, e/w maths, rank; gather finished races for study |
| ai | `reason` | Direct-HTTP model caller. Per-task model TABLE + per-task daily token CEILINGS + global cap + prompt caching + usage ledger. Never a source of facts |
| study | `morningread` `selfcritique` `investigate` `nuances` `naplog` `store` | The learning loop: deep-read prompts (RULE ONE first), night self-interrogation with evidence tools, nuance ledger (dedup-as-votes, clue tracking, 28-day broom, scoreboard), the pick record |
| report | `mail` `restudy` `email_render` | SMTP (never raises), pre-race readouts (pace map, scales, finding-tools) |
| cli | `nap` `learn` `health` `dissect` `brief` `restudy` `napcheck` `_common` | Entry points. Scheduled ones wrapped in `run_guarded` (crash → traceback + email + exit 1) |

Dependency direction: `cli → pipeline/study → selection/domain → data`. Domain
and selection are pure (no I/O) — that's what makes them testable and safe.

## Data stores (`data/` — repo-anchored, never CWD-relative)

| File | Role | Written by |
|---|---|---|
| `nap.db` | THE RECORD: picks, passes-with-reasons, shadow, SP, P/L | 07:30 nap, 22:00 settle |
| `nuances.db` | The learning: nuances (votes/themes), tracked clues (held/missed), rule tally | 22:00 night school |
| `model_usage.csv` | The bill, counted from API responses (cache-aware) | every model call |
| `task_runs.log` | Flight recorder: START/EXIT + full output per run | `trial.sh` |
| `study.db` `ledger.db` `backtest.db` | Old system's history — dormant, kept as record | nothing (since 2026-07-12) |

## Scheduled flows (PythonAnywhere, UTC — `trial.sh`)

- **07:30 `nap`** — read card → evidence → conviction → survivors → deep read
  (3 candidates, model per `ai/reason` table) → bank + email. Passes bank WITH
  their reason.
- **09:30 `health`** — pure-ledger red/green: banked today? settled? nuances
  flowing? broom? spend spikes? truncation? P/L, strike, doorbell.
- **12:30 `guard`** — market drift check on the banked pick (graded bands).
- **22:00 `night`** — settle (results, clues, broom; best-effort) then study
  (nap autopsy + most surprising result → nuances). Sunday adds synthesis.

## Environment variables (all optional unless marked)

- `RACING_API_USERNAME` / `RACING_API_PASSWORD` — **required**; Basic Auth.
- `RACING_API_CARDS` — racecards tier (`pro` default; `standard` after downgrade).
- `RACING_API_HORSE_RESULTS` — pin the histories door (`pro`|`standard`; default
  auto: try pro, demote on plan-gate 401/402/403).
- `ANTHROPIC_API_KEY` — enables the model; absent = engine-only, said out loud.
- `ANTHROPIC_MODEL_<TASK>` > table > `ANTHROPIC_MODEL` — model per task.
- `NAP_TOKEN_BUDGET` (global day cap) / `NAP_TOKEN_BUDGET_<TASK>` — hard stops.
- `EMAIL_SENDER` / `EMAIL_PASSWORD` / `EMAIL_RECIPIENT` / `SMTP_HOST` / `SMTP_PORT`.
- `TRIAL_BRANCH` — branch trial.sh follows.

## Engineering rules of the road

- **Tests gate pushes** (`.github/workflows/tests.yml`). Run locally as
  `PYTHONPATH=src python -m pytest tests/` and CHECK THE EXIT CODE — never
  pipe pytest into another command before `&&`.
- Every regression fix lands with the test that would have caught it, dated
  and commented with the incident (see any `2026-*` comment for the style).
- Optional lenses degrade to OWED; CRITICAL fetches (histories, results) fail
  loud. Know which kind you're touching.
- One behaviour change per commit, REVERT-IF in the message where behaviour
  moves. Refactors that change no behaviour say so.
- The box runs `git pull` before every task — whatever is on the trial branch
  at 07:30 IS the system. Push red, race red.
