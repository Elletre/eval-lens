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
