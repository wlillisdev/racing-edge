"""The homework run — forensically mine every studied race for what separates
winners, and print the report. No API, no DB writes; reads the study DB only.

    python -m racing_edge.cli.homework

Run it after the nightly study has banked a few cards. The more races studied, the
less the numbers lie — treat them as leads to test against the notebook.
"""

from __future__ import annotations

from racing_edge.cli._common import open_study_store
from racing_edge.report.homework import render_homework
from racing_edge.study.homework import analyse_homework


def main() -> int:
    store = open_study_store()
    rows = store.all_studies()
    store.close()
    if not rows:
        print("No studied races yet — run `study` after a card settles, then come back.")
        return 0
    print(render_homework(analyse_homework(rows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
