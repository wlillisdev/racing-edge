-- nap_miss_autopsy — the post-race learning loop, your way: "why didn't I back
-- the winner?" One row per race where OUR NAP didn't win, with the line(s) of
-- the method the winner had that we missed. Idempotent (IF NOT EXISTS).

CREATE TABLE IF NOT EXISTS nap_misses (
  race_id        VARCHAR(40)  NOT NULL,
  miss_date      DATE         NOT NULL,
  course         VARCHAR(80),
  our_pick       VARCHAR(120),
  our_pick_id    VARCHAR(40),
  our_pick_pos   VARCHAR(8),
  our_pick_sp    DECIMAL(8,2),
  winner         VARCHAR(120),
  winner_id      VARCHAR(40),
  winner_sp      DECIMAL(8,2),
  winner_edge    TEXT,
  missed_factors JSON,
  we_had_line    TINYINT,        -- 1 = weighting fault (method has it); 0 = new signal
  was_findable   TINYINT,
  rationale      TEXT,
  prompt_version VARCHAR(8),
  model          VARCHAR(40),
  PRIMARY KEY (race_id, miss_date)
);

CREATE TABLE IF NOT EXISTS nap_miss_patterns (
  factor         VARCHAR(80)  NOT NULL,
  times_missed   INT          NOT NULL,
  findable_count INT          NOT NULL,
  last_seen      DATE,
  PRIMARY KEY (factor)
);
