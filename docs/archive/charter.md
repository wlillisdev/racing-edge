# Racing Edge — what this is, and how it learns

**One line:** an apprentice that does the tireless reading so William does the
deciding — and gets sharper by studying every race. **Not a predictor.**

Read this first. It's the thread. It exists so we never re-walk the dead ends.

---

## What we proved (so we don't relearn it the hard way)

- **Surface stats have no selection edge.** The market already prices the figures
  (ratings, weight, days-since, trainer %). Our own walk-forward test couldn't beat
  the de-vigged market on log-loss; the best study of our exact market — Wilkens
  (2026), UK flat+jumps, Plackett-Luce + LLM trouble-in-running + isotonic — found
  the same, and that the LLM and non-linear layers add nothing to returns.
- **So: do NOT go back to ML / backtesting / crunching old numbers for selection.**
  That is a settled dead end. It launders noise; it does not build judgement.
- **Where an edge can live:** the human's judgement on open, winnable races, *plus*
  tireless grunt work, *plus* price-capture/execution (best price, exchange for
  no-gubbing + BSP), *plus* honest measurement. Amplify the man; don't replace him.

## What this is

An **apprenticeship engine.** AI does the grunt work; **William makes every call.**
Never a black-box score. Never AI picking in a vacuum. The machine reads, assembles,
and studies; the human decides.

## How it works — the loop

1. **Filter** the day's card to a handful of winnable races (race selection before
   horse selection — never NAP a blanket-finish lottery).
2. **Read** the contenders like a detective — every clue assembled: the *finish*
   (manner, not figures), the trip/going/track, the franking, the trainer angle,
   and the **market move** on the shortlist (William's number-one tiebreaker).
3. **William decides.** No forced bet — "best horse found, no bet" is a result.
4. **Study every result vs the picks** that night — the whole card, not just ours.
5. **Bank the recurring lesson** into the notebook → it becomes a check on the next
   pick. The eye compounds, week on week.

## The roles

- **AI:** tireless, never-sloppy grunt work — read every comment, frank every form
  line, watch the market, study every race. A locked door is not an excuse; find
  the window.
- **William:** the call, and the master who marks the homework. He trains the loop.

## The guardrails (how we stay honest and don't repeat mistakes)

- **Study picks-vs-results — never crunch old numbers.** One builds judgement; the
  other launders noise.
- **Paper-test before live.** Prove a brick on real races before it touches a pick.
- **Under-promise on profit.** "Better picks" ≠ "profitable" against an efficient
  market and costs. Keep measuring honestly (CLV / results) even while building the
  eye. Rather under-sell than over-claim.
- **A rule recurs before it's banked.** One race is a cruel photo, not a lesson —
  don't fill the notebook with variance.
- **Don't over-engineer.** Smallest real brick that earns its place. No cathedrals.
- **The human stays the decider.** AI never picks in a black box.

## The memory

- `docs/handicapping_notebook.md` — the earned rules + the learning loop. Grows one
  race at a time. This is the apprentice's "thirty years", made durable.

## Where we are / next

- **Built and tested offline:** the notebook + loop mechanism; `domain/manner.py`
  (read the finish — rule #1, downgrades nearly-types from NAP to place-only);
  `study/postmortem.py` (study every race, test the rules against reality).
- **Next:** paper-test `manner` + `study` on real races (William marking), THEN
  wire the **comments** in on the deployment so `nap_verdict` downgrades nearly-types
  live and `study_card` runs nightly over the full card.

## If you are a future session reading this

This is the agreed approach — pick it up here. **Do not restart the ML / backtest
dead end.** Be the apprentice: read races, study results, bank only recurring rules,
keep William as the decider. The work is on branch `claude/rebuild-v5`.
