-- Three tables: what was run, what happened in each attempt, and what it touched.
-- Wide enough to answer the questions in sql/, narrow enough to read in one screen.

CREATE TABLE IF NOT EXISTS runs
(
    run_id        String,
    project       String,
    suite         String,
    suite_version String,
    variant       String,
    model         String,
    config        String,  -- settings two runs must share before a difference means anything
    recorded_at   String,
    kind          String,  -- model | fixture
    source        String   -- path under data/, so a row can be traced back to its bytes
)
ENGINE = MergeTree
ORDER BY (project, run_id);

CREATE TABLE IF NOT EXISTS trials
(
    run_id        String,
    case_id       String,
    family        String,
    repeat        UInt16,
    passed        UInt8,
    error         String,  -- set when the harness ended the attempt: excluded from rates
    failures      Array(String),
    gates         Map(String, UInt8),  -- empty for a project that records only failures
    tools         Array(String),
    tool_calls    UInt16,
    input_tokens  UInt32,
    output_tokens UInt32,
    seconds       Float64
)
ENGINE = MergeTree
ORDER BY (run_id, case_id, repeat);

CREATE TABLE IF NOT EXISTS tool_calls
(
    run_id  String,
    case_id String,
    repeat  UInt16,
    seq     UInt16,
    name    String,
    ok      UInt8
)
ENGINE = MergeTree
ORDER BY (run_id, case_id, repeat, seq);

CREATE TABLE IF NOT EXISTS comparisons
(
    name      String,
    project   String,
    control   String,  -- run_id everything is measured against
    candidate String,  -- run_id under test
    factor    String   -- what differs between them
)
ENGINE = MergeTree
ORDER BY (project, name);

-- Every case with what it did across its scope: the answer other questions build on.
CREATE VIEW IF NOT EXISTS case_verdicts AS
WITH
graded AS (
    SELECT t.run_id, t.case_id, t.family, t.passed, t.seconds, r.project, r.suite_version, r.kind
    FROM trials AS t
    INNER JOIN runs AS r USING (run_id)
    WHERE t.error = ''
),
case_rate AS (
    SELECT project, suite_version, run_id, case_id, kind,
           any(family) AS family, avg(passed) AS rate, avg(seconds) AS seconds
    FROM graded
    GROUP BY project, suite_version, run_id, case_id, kind
),
paired AS (
    SELECT concat(l.project, '|', l.suite_version, '|', l.case_id) AS scoped_case,
           l.rate != r.rate AS moved
    FROM comparisons AS c
    INNER JOIN case_rate AS l ON l.run_id = c.control
    INNER JOIN case_rate AS r ON r.run_id = c.candidate AND r.case_id = l.case_id
),
verdict AS (
    SELECT scoped_case, count() AS comparisons, sum(moved) AS discriminated
    FROM paired
    GROUP BY scoped_case
),
observed AS (
    SELECT concat(project, '|', suite_version, '|', case_id) AS scoped_case,
           project, suite_version, case_id,
           any(family) AS family,
           min(rate) AS lowest, max(rate) AS highest, avg(seconds) AS seconds
    FROM case_rate
    WHERE kind = 'model'
    GROUP BY project, suite_version, case_id
)
SELECT
    o.project AS project,
    o.suite_version AS suite_version,
    o.case_id AS case_id,
    o.family AS family,
    ifNull(v.comparisons, 0) AS comparisons,
    ifNull(v.discriminated, 0) AS discriminated,
    multiIf(
        ifNull(v.discriminated, 0) > 0, 'informative',
        o.lowest = 1, 'saturated',
        o.highest = 0, 'floored',
        'quiet'
    ) AS label,
    round(o.seconds, 6) AS seconds
FROM observed AS o
LEFT JOIN verdict AS v ON v.scoped_case = o.scoped_case;
