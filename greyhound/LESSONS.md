# Calibration Journal — the memory of this system

Every result autopsy writes an entry here. This file is the system's
long-term memory: chat sessions end, this survives. **Read this before
scoring any card. Add an entry after every logged result that taught
something. Never delete entries — superseded lessons get struck through
with a note, because knowing what we used to believe wrongly is also
knowledge.**

The loop, always in this order:

1. Score the card BEFORE the race. The engine's call is the logged call.
2. Log the result with `log_result.py` BEFORE touching the scorer — the
   log records what the method believed at prediction time. No revisionism.
3. Autopsy: join the dots between the form lines and the result comment.
4. Only encode a fix if it's a GENERAL form-reading truth the result
   exposed — never a patch that merely makes one race come right.
5. Commit with the lesson in the message.

---

## 2026-07-03 — Cork R2 (A7 525): engine pick 5th, winner was our 3rd at 5/2

**Result:** 1st Ballysloe Archie (T6, 5/2, "Ld 1, drclr"), 2nd Clongeel
Swannie (T4, EVENS, 2 career starts), 3rd Rosstemple Bowi, 5th Klassy
Jack (engine's pick, "SlAw, NvShw" — again).

**Lesson 1 — stale class times are ghosts.** Klassy Jack topped the
clock (29.86 in old A5 company) and had a +9 grade drop. But he was
0-for-11 career, beaten 7-11L in his recent runs with NO trouble
comments, NvShw three times. The grader wasn't giving him easier races;
the grader was chasing him downhill. *Encoded: grade drops only score as
opportunity when the beaten runs carry excuses; drop demotion is
exempted when the latest run was a win (that's not a declining dog).*

**Lesson 2 — warnings multiply.** Chronic non-winner + poor draw record
+ decline drop + slow-away habit: any three together mean the numbers
overrate the dog. *Encoded: RED FLAGS STACK, −5.*

**Lesson 3 — the freshest runs carry the trip signal.** Archie's two
most recent runs were sprints (QAw, EP) — speed being sharpened for a
step back up. Three year-old route runs buried that under a majority
vote. *Encoded: trip change reads the last 1–2 runs only.*

**Lesson 4 — no split ≠ no pace opinion.** Sprint lines print no
sectional, but "22" first calls and QAw comments said Archie would lead
the bend. He did, by the first turn, race over. *Encoded: pace inferred
from comments/first-calls when splits are missing.*

**Lesson 5 — the market sees the trials.** Swannie: 2 career starts,
form book nearly empty, three trials — and sent off at EVENS. Connections
knew. *Encoded: market_whisper flag when forecast odds ≤ 2.5 on a ≤4-start
dog. Get forecast prices onto cards whenever possible.*

**Lesson 6 — results-page "By" is margin-to-next, not total.** EstTm in
results is cumulative. Don't mis-transcribe when logging.

**Open question for future results:** wide seed in T6 won while five
railers scrimmaged — one datapoint toward a Cork 525 outside bias.
Bias table at 1/30. Do not act on it yet.

---

## 2026-07-03 — teaching session (pre-results), source: the owner

The human patterns encoded this session, in his words paraphrased:

- Comments are the form line's confession: Crd/Blk/Bmp in a beaten run
  is an excuse; StyWl/RnOn is a dog that keeps finding; Fd is one that
  empties; SlAw/QAw are habits.
- Splits only compare within same track + same trip (Youghal ~4.2s vs
  Cork ~3.4s at "525") and recent (≤365d).
- EstTm = WinTm + 0.07s/length beaten + signed going allowance. Verified
  to ±0.01s against four printed values.
- A dog dropped in grade to weaker company can bob up — especially when
  the drop came from trouble, not decline.
- Trip drops suit early-pace dogs (get home easily); trip rises suit
  strong finishers.
- Trk column: track lovers (score wins/places HERE) and raiders — a
  Kerry dog shipped to Cork travelled with intent. Raiders arrive blind
  on the clock; flag loudly, learn their treatment from results.
- Tp column: some dogs run better inside or outside regardless of
  seeding — score tonight's draw against the dog's own draw history.
- By column: beaten a short head/half-length = a stride from winning; a
  near-miss from a conceded break turns around with a level break.
- Sts columns: winning is a habit, losing more so — 0 wins in 8+ starts
  is a proven non-winner.
- Cork draw bias: inside vs outside — LEARN it from logged results
  (30+ races), never guess it.

## Standing rules

- Weights are uncalibrated until the results log supports a band
  analysis (~100 races), same methodology that found the horse system's
  profitable 70–79 band. Until then: every race gets a call + confidence,
  stakes stay nominal.
- The engine argues, the log arbitrates. When the engine and the
  form-reader disagree (R2: engine Klassy Jack, reader Bowi, winner
  neither), say both out loud before the race — disagreement races are
  the highest-information calibration points.
