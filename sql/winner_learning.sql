-- winner_learning.sql — storage for the daily open-eyes winner-learning loop (Track A).
-- Lives in the existing warehouse. Run once:
--   mysql -u USER -p DBNAME < sql/winner_learning.sql
-- Idempotent (IF NOT EXISTS); safe to re-run.

-- Per-winner open-eyes read + post-result explanation.
CREATE TABLE IF NOT EXISTS winner_reads (
    id               INT          NOT NULL AUTO_INCREMENT,
    race_id          VARCHAR(50)  NOT NULL COMMENT 'FK -> races.race_id',
    horse_id         VARCHAR(50)  NOT NULL COMMENT 'Winning horse',
    read_date        DATE         NOT NULL COMMENT 'Race date',
    course           VARCHAR(100) NULL,
    horse_name       VARCHAR(100) NULL,
    sp_decimal       FLOAT        NULL     COMMENT 'Result SP (revealed only in stage 3)',
    blind_assessment TEXT         NULL     COMMENT 'Stage 1: open-eyes pre-race read, no result shown',
    blind_likelihood VARCHAR(10)  NULL     COMMENT 'high / medium / low predicted pre-race',
    decisive_factor  VARCHAR(255) NULL     COMMENT 'Stage 3: single biggest reason it won',
    winning_factors  TEXT         NULL     COMMENT 'Stage 3: JSON array of contributing factors',
    was_findable     TINYINT(1)   NULL     COMMENT '1 if the blind read would have flagged it',
    rationale        TEXT         NULL     COMMENT 'Stage 3: why it won',
    prompt_version   VARCHAR(20)  NULL     COMMENT 'Prompt version for reproducibility',
    model            VARCHAR(40)  NULL     COMMENT 'Model used for the reads',
    created_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_winner_read (race_id, horse_id),
    INDEX idx_winner_read_date (read_date),
    INDEX idx_winner_findable  (was_findable)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Aggregated winning patterns (rebuilt from winner_reads).
CREATE TABLE IF NOT EXISTS winning_patterns (
    id              INT          NOT NULL AUTO_INCREMENT,
    factor          VARCHAR(255) NOT NULL COMMENT 'Normalised winning-factor tag',
    occurrences     INT          NOT NULL DEFAULT 0 COMMENT 'Winners exhibiting this factor',
    findable_count  INT          NOT NULL DEFAULT 0 COMMENT 'Of those, how many the blind read caught',
    last_seen       DATE         NULL,
    updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_pattern (factor),
    INDEX idx_pattern_occ (occurrences)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
