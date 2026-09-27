"""The full-field archive behind docs/RULEBOOK_TEST.md (2026-09-27).

The first rulebook test ran on a corpus with no draw, weight, mark or going,
and on 185 scattered days, so half his rules could not be tested and the
rest were tested on broken histories. The archive fixes both. These tests
pin that it is present and carries the fields the rules need, so a later
edit cannot quietly strip it back to the old shape."""
import csv
import gzip
from pathlib import Path

from racing_edge.school import rulebook_test as RT

ARCHIVE = Path(RT.ARCHIVE)


def test_the_archive_carries_the_fields_his_rules_need():
    with gzip.open(ARCHIVE, "rt", newline="") as fh:
        head = next(csv.reader(fh))
    for col in ("draw", "weight_lbs", "or", "age", "going", "class", "sp_dec", "position"):
        assert col in head, f"the archive lost {col} — the rules that read it go blind"


def test_the_archive_is_whole_not_scattered_days():
    races = RT.load_archive()
    assert len(races) >= 9600
    days = {r["date"] for r in races}
    assert len(days) >= 260, "history needs every day, not a scatter of them"
    assert min(days) <= "2026-01-01" and max(days) >= "2026-09-26"
