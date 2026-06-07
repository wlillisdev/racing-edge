-- =============================================================================
-- schema.sql — Racing Edge evidence warehouse
--
-- MySQL 8.x / PythonAnywhere compatible.
-- All tables use IF NOT EXISTS so this file is idempotent and safe to re-run.
-- Character set: utf8mb4 throughout for full Unicode support (horse names,
-- jockey names with diacritics, etc.).
-- =============================================================================

SET NAMES utf8mb4;
SET CHARACTER SET utf8mb4;

-- =============================================================================
-- 1. system_runs — one row per pipeline / module execution
-- =============================================================================
CREATE TABLE IF NOT EXISTS system_runs (
    id              INT             NOT NULL AUTO_INCREMENT,
    script          VARCHAR(100)    NOT NULL COMMENT 'Name of the script / module that ran',
    run_date        DATE            NOT NULL COMMENT 'Calendar date of the run (YYYY-MM-DD)',
    run_ts          DATETIME        NOT NULL COMMENT 'Exact start timestamp of the run',
    status          ENUM(
                        'pass',
                        'fail',
                        'blocked'
                    )               NOT NULL COMMENT 'pass=completed OK, fail=error, blocked=missing prereqs',
    reports_created TEXT            NULL     COMMENT 'Comma-separated list of report filenames written',
    errors          TEXT            NULL     COMMENT 'Error messages or exception text, if any',
    duration_secs   FLOAT           NULL     COMMENT 'Wall-clock run time in seconds',

    PRIMARY KEY (id),
    INDEX idx_system_runs_run_date  (run_date),
    INDEX idx_system_runs_script    (script),
    INDEX idx_system_runs_status    (status)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='Audit log of every pipeline script execution';


-- =============================================================================
-- 2. races — one row per race
-- =============================================================================
CREATE TABLE IF NOT EXISTS races (
    id              INT             NOT NULL AUTO_INCREMENT,
    race_id         VARCHAR(50)     NOT NULL COMMENT 'Unique race identifier from the Racing API',
    race_date       DATE            NOT NULL COMMENT 'Date the race takes place',
    off_time        TIME            NULL     COMMENT 'Scheduled off time (HH:MM:SS)',
    course          VARCHAR(100)    NULL     COMMENT 'Racecourse name',
    region          VARCHAR(10)     NULL     COMMENT 'Region code, e.g. gb, ire',
    race_name       VARCHAR(255)    NULL     COMMENT 'Full race title',
    race_class      VARCHAR(20)     NULL     COMMENT 'Class 1-6, Listed, Group 1-3, etc.',
    race_type       VARCHAR(50)     NULL     COMMENT 'Flat / Hurdle / Chase / NH Flat',
    distance_f      FLOAT           NULL     COMMENT 'Race distance in furlongs',
    going           VARCHAR(50)     NULL     COMMENT 'Normalised going description',
    surface         VARCHAR(20)     NULL     COMMENT 'Turf / AW (All-Weather)',
    field_size      INT             NULL     COMMENT 'Number of declared runners',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    UNIQUE KEY uq_races_race_id     (race_id),
    INDEX idx_races_race_date       (race_date),
    INDEX idx_races_course          (course),
    INDEX idx_races_region          (region)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='Master list of races';


-- =============================================================================
-- 3. runners — one row per runner per race
-- =============================================================================
CREATE TABLE IF NOT EXISTS runners (
    id              INT             NOT NULL AUTO_INCREMENT,
    race_id         VARCHAR(50)     NOT NULL COMMENT 'FK → races.race_id',
    horse_id        VARCHAR(50)     NOT NULL COMMENT 'API horse identifier',
    horse_name      VARCHAR(100)    NULL     COMMENT 'Horse name',
    trainer         VARCHAR(100)    NULL     COMMENT 'Trainer name',
    jockey          VARCHAR(100)    NULL     COMMENT 'Jockey name',
    age             VARCHAR(10)     NULL     COMMENT 'Age (may include qualifier, e.g. "4")',
    sex             VARCHAR(5)      NULL     COMMENT 'G / M / F / C / H / R',
    draw            INT             NULL     COMMENT 'Stall draw (NULL for jumps)',
    weight_lbs      INT             NULL     COMMENT 'Carried weight in pounds',
    official_rating INT             NULL     COMMENT 'Official handicap rating',
    rpr             INT             NULL     COMMENT 'Racing Post Rating',
    ts_rating       INT             NULL     COMMENT 'Topspeed rating',
    sp_morning      FLOAT           NULL     COMMENT 'Morning line SP (decimal)',
    sp_latest       FLOAT           NULL     COMMENT 'Latest pre-race SP (decimal)',
    sp_starting     FLOAT           NULL     COMMENT 'Starting price (decimal)',
    form_string     VARCHAR(50)     NULL     COMMENT 'Raw form string from racecard',
    last_run_days   INT             NULL     COMMENT 'Days since last run',

    PRIMARY KEY (id),
    UNIQUE KEY uq_runners_race_horse    (race_id, horse_id),
    INDEX idx_runners_horse_id          (horse_id),
    INDEX idx_runners_race_id           (race_id),
    INDEX idx_runners_trainer           (trainer),
    INDEX idx_runners_jockey            (jockey),
    CONSTRAINT fk_runners_race_id
        FOREIGN KEY (race_id)
        REFERENCES races (race_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='Individual runner entries within each race';


-- =============================================================================
-- 4. model_candidates — NAP / value_ew / watchlist / shadow selections
-- =============================================================================
CREATE TABLE IF NOT EXISTS model_candidates (
    id              INT             NOT NULL AUTO_INCREMENT,
    candidate_date  DATE            NOT NULL COMMENT 'Date the candidate was identified',
    horse_id        VARCHAR(50)     NOT NULL COMMENT 'API horse identifier',
    horse_name      VARCHAR(100)    NULL     COMMENT 'Horse name',
    race_id         VARCHAR(50)     NOT NULL COMMENT 'Race the candidate runs in',
    course          VARCHAR(100)    NULL     COMMENT 'Racecourse name',
    off_time        TIME            NULL     COMMENT 'Scheduled off time',
    candidate_type  ENUM(
                        'nap',
                        'value_ew',
                        'best_of_card',
                        'watchlist',
                        'shadow',
                        'no_bet'
                    )               NOT NULL COMMENT 'Selection classification',
    grade           VARCHAR(5)      NULL     COMMENT 'A / B / C grade for the selection quality',
    score           FLOAT           NULL     COMMENT 'Model composite score',
    model_version   VARCHAR(20)     NULL     COMMENT 'Model version that produced this candidate',
    reasons         TEXT            NULL     COMMENT 'JSON or pipe-delimited list of qualifying reasons',
    warnings        TEXT            NULL     COMMENT 'JSON or pipe-delimited list of risk flags',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    INDEX idx_candidates_date           (candidate_date),
    INDEX idx_candidates_horse_id       (horse_id),
    INDEX idx_candidates_race_id        (race_id),
    INDEX idx_candidates_type           (candidate_type),
    INDEX idx_candidates_date_type      (candidate_date, candidate_type)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='Model output — daily NAP, value EW, watchlist etc.';


-- =============================================================================
-- 5. odds_snapshots — morning / late / SP price captures
-- =============================================================================
CREATE TABLE IF NOT EXISTS odds_snapshots (
    id              INT             NOT NULL AUTO_INCREMENT,
    snapshot_date   DATE            NOT NULL COMMENT 'Date of the snapshot',
    horse_id        VARCHAR(50)     NOT NULL COMMENT 'API horse identifier',
    race_id         VARCHAR(50)     NOT NULL COMMENT 'Race identifier',
    snapshot_type   ENUM(
                        'morning',
                        'late',
                        'sp'
                    )               NOT NULL COMMENT 'When in the day this price was captured',
    odds_decimal    FLOAT           NULL     COMMENT 'Price in decimal format (e.g. 4.5)',
    odds_fractional VARCHAR(20)     NULL     COMMENT 'Price in fractional format (e.g. 7/2)',
    snapshot_ts     DATETIME        NOT NULL COMMENT 'Exact timestamp of capture',
    source          VARCHAR(50)     NULL     COMMENT 'Bookmaker or exchange source',

    PRIMARY KEY (id),
    INDEX idx_odds_date             (snapshot_date),
    INDEX idx_odds_horse_id         (horse_id),
    INDEX idx_odds_race_id          (race_id),
    INDEX idx_odds_date_type        (snapshot_date, snapshot_type),
    INDEX idx_odds_horse_date       (horse_id, snapshot_date)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='Historical price snapshots for market movement analysis';


-- =============================================================================
-- 6. market_moves — movement classifications between morning and late prices
-- =============================================================================
CREATE TABLE IF NOT EXISTS market_moves (
    id              INT             NOT NULL AUTO_INCREMENT,
    move_date       DATE            NOT NULL COMMENT 'Date of the race',
    horse_id        VARCHAR(50)     NOT NULL COMMENT 'API horse identifier',
    race_id         VARCHAR(50)     NOT NULL COMMENT 'Race identifier',
    horse_name      VARCHAR(100)    NULL     COMMENT 'Horse name',
    morning_odds    FLOAT           NULL     COMMENT 'Morning line decimal odds',
    late_odds       FLOAT           NULL     COMMENT 'Late decimal odds (nearest to off)',
    pct_change      FLOAT           NULL     COMMENT '% price change (negative = steaming in)',
    move_type       ENUM(
                        'strong_steamer',
                        'steamer',
                        'late_support',
                        'stable',
                        'weak_drift',
                        'dangerous_drift',
                        'false_gamble'
                    )               NOT NULL COMMENT 'Classified movement type',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    INDEX idx_moves_date            (move_date),
    INDEX idx_moves_horse_id        (horse_id),
    INDEX idx_moves_race_id         (race_id),
    INDEX idx_moves_type            (move_type),
    INDEX idx_moves_date_type       (move_date, move_type)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='Classified market movements from morning to late price';


-- =============================================================================
-- 7. results — race results (populated after races are run)
-- =============================================================================
CREATE TABLE IF NOT EXISTS results (
    id              INT             NOT NULL AUTO_INCREMENT,
    race_id         VARCHAR(50)     NOT NULL COMMENT 'Race identifier',
    horse_id        VARCHAR(50)     NOT NULL COMMENT 'API horse identifier',
    horse_name      VARCHAR(100)    NULL     COMMENT 'Horse name',
    result_date     DATE            NOT NULL COMMENT 'Date the race was run',
    position        INT             NULL     COMMENT 'Finishing position (NULL = non-runner / void)',
    beaten_lengths  FLOAT           NULL     COMMENT 'Distances beaten by winner (0.0 if won)',
    sp_decimal      FLOAT           NULL     COMMENT 'Starting price in decimal format',
    won             TINYINT(1)      NULL     COMMENT '1 if finished 1st',
    placed          TINYINT(1)      NULL     COMMENT '1 if finished in the places (top 3 or EW terms)',
    was_nap         TINYINT(1)      NOT NULL DEFAULT 0 COMMENT '1 if this was the model NAP',
    was_value_ew    TINYINT(1)      NOT NULL DEFAULT 0 COMMENT '1 if this was the model value EW pick',
    official_stake  FLOAT           NOT NULL DEFAULT 0 COMMENT 'Notional stake used for P&L tracking',
    official_pl     FLOAT           NOT NULL DEFAULT 0 COMMENT 'Profit/loss on official_stake',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    UNIQUE KEY uq_results_race_horse    (race_id, horse_id),
    INDEX idx_results_date              (result_date),
    INDEX idx_results_horse_id          (horse_id),
    INDEX idx_results_race_id           (race_id),
    INDEX idx_results_was_nap           (was_nap),
    INDEX idx_results_was_value_ew      (was_value_ew)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='Post-race results with P&L tracking for model selections';


-- =============================================================================
-- 8. trainer_market_profiles — aggregated trainer performance by move type
-- =============================================================================
CREATE TABLE IF NOT EXISTS trainer_market_profiles (
    id              INT             NOT NULL AUTO_INCREMENT,
    trainer         VARCHAR(100)    NOT NULL COMMENT 'Trainer name',
    move_type       VARCHAR(50)     NOT NULL COMMENT 'Market movement classification',
    sample_size     INT             NOT NULL DEFAULT 0 COMMENT 'Number of runners in this cell',
    wins            INT             NOT NULL DEFAULT 0 COMMENT 'Number of winners',
    places          INT             NOT NULL DEFAULT 0 COMMENT 'Number of placed finishes',
    win_pct         FLOAT           NOT NULL DEFAULT 0 COMMENT 'Win strike rate (0-100)',
    place_pct       FLOAT           NOT NULL DEFAULT 0 COMMENT 'Place strike rate (0-100)',
    roi             FLOAT           NOT NULL DEFAULT 0 COMMENT 'Return on investment (level stakes, decimal)',
    last_updated    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
                                    ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    UNIQUE KEY uq_trainer_move      (trainer, move_type),
    INDEX idx_trainer_profiles_trainer  (trainer),
    INDEX idx_trainer_profiles_move     (move_type)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='Per-trainer win/place/ROI statistics broken down by market move type';


-- =============================================================================
-- 9. form_strength_records — daily form assessment per runner
-- =============================================================================
CREATE TABLE IF NOT EXISTS form_strength_records (
    id              INT             NOT NULL AUTO_INCREMENT,
    assessment_date DATE            NOT NULL COMMENT 'Date the assessment was made',
    horse_id        VARCHAR(50)     NOT NULL COMMENT 'API horse identifier',
    race_id         VARCHAR(50)     NOT NULL COMMENT 'Race the horse is entered in',
    form_score      FLOAT           NULL     COMMENT 'Composite form strength score',
    form_trend      VARCHAR(20)     NULL     COMMENT 'improving / declining / consistent / mixed',
    relevance_score FLOAT           NULL     COMMENT 'How relevant past form is to today (0-1)',
    around_horse_form TEXT          NULL     COMMENT 'JSON summary of beaten / beaten-by horses form',
    hidden_positive TEXT            NULL     COMMENT 'Narrative of any hidden positives found',
    flattered_risk  TINYINT(1)      NOT NULL DEFAULT 0 COMMENT '1 if form may be flattering',
    created_at      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    INDEX idx_form_date             (assessment_date),
    INDEX idx_form_horse_id         (horse_id),
    INDEX idx_form_race_id          (race_id),
    INDEX idx_form_date_horse       (assessment_date, horse_id)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='Form strength assessments produced by the form analyser module';


-- =============================================================================
-- 10. horse_tracker_records — future-race follow notes
-- =============================================================================
CREATE TABLE IF NOT EXISTS horse_tracker_records (
    id                  INT             NOT NULL AUTO_INCREMENT,
    flagged_date        DATE            NOT NULL COMMENT 'Date the horse was flagged to watch',
    horse_id            VARCHAR(50)     NOT NULL COMMENT 'API horse identifier',
    horse_name          VARCHAR(100)    NULL     COMMENT 'Horse name',
    flag_reason         TEXT            NULL     COMMENT 'Why this horse was flagged (free text)',
    required_conditions TEXT            NULL     COMMENT 'Conditions needed before betting (going, distance, etc.)',
    status              ENUM(
                            'watching',
                            'activated',
                            'expired',
                            'retired'
                        )               NOT NULL DEFAULT 'watching',
    follow_up_date      DATE            NULL     COMMENT 'Date to revisit this tracker entry',
    result_when_watched TEXT            NULL     COMMENT 'Result notes if we backed or observed',
    created_at          DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    INDEX idx_tracker_flagged_date      (flagged_date),
    INDEX idx_tracker_horse_id          (horse_id),
    INDEX idx_tracker_status            (status),
    INDEX idx_tracker_follow_up         (follow_up_date)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='Horses flagged for future monitoring with conditional activation notes';


-- =============================================================================
-- 11. angle_performance — angle validation and strike-rate tracking
-- =============================================================================
CREATE TABLE IF NOT EXISTS angle_performance (
    id              INT             NOT NULL AUTO_INCREMENT,
    angle_name      VARCHAR(100)    NOT NULL COMMENT 'Unique identifier for the angle (e.g. trainer_move_steamer)',
    sample_size     INT             NOT NULL DEFAULT 0 COMMENT 'Total qualifying runners seen',
    wins            INT             NOT NULL DEFAULT 0 COMMENT 'Winners from qualifying runners',
    places          INT             NOT NULL DEFAULT 0 COMMENT 'Placed finishes from qualifying runners',
    strike_rate     FLOAT           NOT NULL DEFAULT 0 COMMENT 'Win strike rate (0-100)',
    place_rate      FLOAT           NOT NULL DEFAULT 0 COMMENT 'Place strike rate (0-100)',
    roi             FLOAT           NOT NULL DEFAULT 0 COMMENT 'Level-stakes ROI (decimal)',
    ae_ratio        FLOAT           NOT NULL DEFAULT 0 COMMENT 'Actual vs expected winners ratio (>1 = beating market)',
    status          ENUM(
                        'learning',
                        'watch_angle',
                        'active',
                        'downgraded'
                    )               NOT NULL DEFAULT 'learning'
                    COMMENT 'learning=<30 samples, watch_angle=30-99, active=100+, downgraded=ROI negative',
    last_updated    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
                                    ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    UNIQUE KEY uq_angle_name        (angle_name),
    INDEX idx_angle_status          (status),
    INDEX idx_angle_roi             (roi)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='Running performance statistics for each betting angle tracked by the model';
