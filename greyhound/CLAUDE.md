# Greyhound engine — session bootstrap

Before doing ANY work in this directory:

1. Read `LESSONS.md` — it is the system's memory. The autopsy loop and
   all encoded tradecraft live there. Follow its standing rules.
2. `scorer.py` is the engine; `card_template.json` is the input schema;
   `log_result.py` logs results and feeds the learned draw-bias table.
3. The owner teaches patterns conversationally — encode each one as a
   scored component or flag, test it on a real card, record it in
   LESSONS.md, and commit with the lesson in the message.
4. Log results against the ORIGINAL prediction before changing the
   scorer. Never let a method change rewrite what was predicted.
5. Cards are hand-entered from grireland.ie pastes (no API access).
   Distances in yards, grades A1–A9/S, times use 0.07s per length.
