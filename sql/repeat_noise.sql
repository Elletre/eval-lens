-- How often a run disagrees with itself: cases whose repeats did not all land the same
-- way, under settings that did not change between them.
WITH graded AS (
    SELECT run_id, case_id, passed FROM trials WHERE error = ''
),
per_case AS (
    SELECT run_id, case_id, count() AS repeats, uniqExact(passed) AS verdicts
    FROM graded
    GROUP BY run_id, case_id
)
SELECT
    run_id,
    countIf(repeats > 1) AS cases_with_repeats,
    countIf(repeats > 1 AND verdicts > 1) AS mixed_cases,
    sum(repeats) AS trials
FROM per_case
GROUP BY run_id
ORDER BY run_id;
