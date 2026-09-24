-- How much of a suite's running time went to cases that never separated two sides.
-- Cases no comparison ever used are counted apart: nothing asked them a question.
WITH cost AS (
    SELECT r.project AS project, r.suite_version AS suite_version, t.case_id AS case_id,
           sum(t.seconds) AS seconds
    FROM trials AS t
    INNER JOIN runs AS r USING (run_id)
    WHERE t.error = ''
    GROUP BY project, suite_version, case_id
)
SELECT
    v.project AS project,
    v.suite_version AS suite_version,
    countIf(v.comparisons > 0 AND v.label = 'informative') AS informative_cases,
    countIf(v.comparisons > 0 AND v.label != 'informative') AS silent_cases,
    countIf(v.comparisons = 0) AS uncompared_cases,
    round(sumIf(ifNull(c.seconds, 0), v.comparisons > 0 AND v.label = 'informative'), 6) AS informative_seconds,
    round(sumIf(ifNull(c.seconds, 0), v.comparisons > 0 AND v.label != 'informative'), 6) AS silent_seconds
FROM case_verdicts AS v
LEFT JOIN cost AS c
    ON c.project = v.project AND c.suite_version = v.suite_version AND c.case_id = v.case_id
GROUP BY project, suite_version
ORDER BY project, suite_version;
