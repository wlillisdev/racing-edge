# THE SHAPE BOOK — where winners come from, by race type

(The master, 2026-08-30: "I have seen a similar race previously...
know from experience that this type of race the winner will come
from 2nd or 3rd favourite, or the fav is a good thing... have this
stored and building on it." His memory, rebuilt from the record.
Corpus: 1690 races with a priced field, cells shown at n>=30. Regenerate after each settled stretch: `PYTHONPATH=src python -m racing_edge.school.shapebook`.
V1 limit named: no handicap/non-handicap split yet — the raw rows
carry no flag; joins at the next corpus refresh.)

READ IT LIKE THE MASTER DOES: 'fav%' answers "is the jolly a good
thing in this shape?"; 'top3%' answers "does the winner come from
the front of the market?"; a LOW top3% shape is an anything-can-
win lottery — the shape itself says pass or go bandit-hunting.

| shape (type · class · field · fav) | n | fav% | 2nd fav% | 3rd fav% | top3% | outside% | med win SP | THE GLANCE |
|---|---|---|---|---|---|---|---|---|
| flat · Cl6+ · 8-11 · fav 6/4-3/1 | 204 | 32 | 16 | 16 | 64 | 36 | 4.5 | BEST AVOIDED — lottery shape; never a nap, bandit water only |
| flat · Cl3-4 · 2-7 · fav<6/4 | 141 | 55 | 26 | 13 | 94 | 6 | 2.2 | GET ON THE JOLLY — the fav is a good thing; don't get clever |
| flat · Cl5 · 8-11 · fav 6/4-3/1 | 93 | 29 | 18 | 17 | 65 | 35 | 5.5 | BEST AVOIDED — lottery shape; never a nap, bandit water only |
| flat · Cl5 · 2-7 · fav<6/4 | 79 | 48 | 19 | 13 | 80 | 20 | 2.5 | FULL READ DECIDES — no strong shape prior |
| flat · Cl3-4 · 8-11 · fav<6/4 | 76 | 46 | 21 | 11 | 78 | 22 | 2.5 | FULL READ DECIDES — no strong shape prior |
| C · Cl3-4 · 2-7 · fav 6/4-3/1 | 75 | 45 | 20 | 21 | 87 | 13 | 3.5 | GET ON THE JOLLY — the fav is a good thing; don't get clever |
| flat · Cl3-4 · 2-7 · fav 6/4-3/1 | 73 | 38 | 19 | 15 | 73 | 27 | 3.8 | FULL READ DECIDES — no strong shape prior |
| H · Cl3-4 · 8-11 · fav 6/4-3/1 | 69 | 28 | 30 | 12 | 70 | 30 | 4.3 | FULL READ DECIDES — no strong shape prior |
| flat · Cl3-4 · 8-11 · fav 6/4-3/1 | 69 | 29 | 22 | 12 | 62 | 38 | 4.5 | BEST AVOIDED — lottery shape; never a nap, bandit water only |
| flat · Cl5 · 2-7 · fav 6/4-3/1 | 68 | 32 | 22 | 10 | 65 | 35 | 4.3 | BEST AVOIDED — lottery shape; never a nap, bandit water only |
| flat · Cl6+ · 2-7 · fav 6/4-3/1 | 68 | 31 | 29 | 19 | 79 | 21 | 4.0 | GEM BEHIND THE JOLLY — front of market but often NOT the fav: 2nd-3rd fav hunting ground |
| flat · Cl6+ · 8-11 · fav<6/4 | 65 | 43 | 23 | 11 | 77 | 23 | 3.5 | FULL READ DECIDES — no strong shape prior |
| H · Cl3-4 · 2-7 · fav<6/4 | 60 | 60 | 18 | 15 | 93 | 7 | 2.2 | GET ON THE JOLLY — the fav is a good thing; don't get clever |
| H · Cl3-4 · 8-11 · fav<6/4 | 59 | 51 | 27 | 17 | 95 | 5 | 2.4 | GET ON THE JOLLY — the fav is a good thing; don't get clever |
| C · Cl3-4 · 2-7 · fav<6/4 | 47 | 40 | 34 | 9 | 83 | 17 | 3.0 | FULL READ DECIDES — no strong shape prior |
| flat · Cl6+ · 2-7 · fav<6/4 | 44 | 45 | 36 | 14 | 95 | 5 | 2.8 | GET ON THE JOLLY — the fav is a good thing; don't get clever |
| flat · unclassed · 12-15 · fav 6/4-3/1 | 41 | 37 | 17 | 12 | 66 | 34 | 4.5 | FULL READ DECIDES — no strong shape prior |
| H · Cl3-4 · 2-7 · fav 6/4-3/1 | 40 | 40 | 28 | 12 | 80 | 20 | 3.9 | FULL READ DECIDES — no strong shape prior |
| H · unclassed · 2-7 · fav<6/4 | 35 | 49 | 37 | 9 | 94 | 6 | 2.4 | GET ON THE JOLLY — the fav is a good thing; don't get clever |
| C · Cl5 · 2-7 · fav 6/4-3/1 | 34 | 29 | 29 | 21 | 79 | 21 | 4.4 | GEM BEHIND THE JOLLY — front of market but often NOT the fav: 2nd-3rd fav hunting ground |
| C · Cl5 · 2-7 · fav<6/4 | 32 | 59 | 22 | 6 | 88 | 12 | 2.2 | GET ON THE JOLLY — the fav is a good thing; don't get clever |
| H · unclassed · 8-11 · fav 6/4-3/1 | 32 | 31 | 25 | 16 | 72 | 28 | 4.5 | FULL READ DECIDES — no strong shape prior |
| H · Cl5 · 2-7 · fav 6/4-3/1 | 32 | 34 | 28 | 25 | 88 | 12 | 4.2 | GEM BEHIND THE JOLLY — front of market but often NOT the fav: 2nd-3rd fav hunting ground |
| flat · unclassed · 12-15 · fav>3/1 | 32 | 34 | 9 | 16 | 59 | 41 | 5.8 | BEST AVOIDED — lottery shape; never a nap, bandit water only |
| H · unclassed · 12-15 · fav 6/4-3/1 | 31 | 16 | 19 | 10 | 45 | 55 | 7.0 | BEST AVOIDED — lottery shape; never a nap, bandit water only |
| flat · unclassed · 8-11 · fav 6/4-3/1 | 31 | 29 | 23 | 3 | 55 | 45 | 4.3 | BEST AVOIDED — lottery shape; never a nap, bandit water only |
| H · Cl5 · 8-11 · fav 6/4-3/1 | 30 | 30 | 23 | 20 | 73 | 27 | 4.8 | FULL READ DECIDES — no strong shape prior |
| C · unclassed · 2-7 · fav<6/4 | 30 | 57 | 20 | 7 | 83 | 17 | 2.2 | FULL READ DECIDES — no strong shape prior |
