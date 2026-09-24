-- The same variant scored more than once, with something else changed: the floor under
-- any difference this suite reports.
WITH graded AS (
    SELECT t.run_id, t.case_id, t.passed, r.project, r.suite_version, r.variant, r.model, r.config
    FROM trials AS t
    INNER JOIN runs AS r USING (run_id)
    WHERE t.error = '' AND r.kind = 'model'
),
case_rate AS (
    SELECT project, suite_version, variant, model, config, run_id, case_id, avg(passed) AS rate
    FROM graded
    GROUP BY project, suite_version, variant, model, config, run_id, case_id
),
run_rate AS (
    SELECT project, suite_version, variant, model, config, run_id, avg(rate) AS rate
    FROM case_rate
    GROUP BY project, suite_version, variant, model, config, run_id
)
SELECT
    project,
    suite_version,
    variant,
    model,
    count() AS runs,
    round(max(rate) - min(rate), 6) AS spread
FROM run_rate
GROUP BY project, suite_version, variant, model
HAVING runs > 1
ORDER BY project, suite_version, variant, model;
