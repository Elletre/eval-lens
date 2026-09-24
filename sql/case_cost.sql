-- What each case costs to ask, summed over every run that asked it.
SELECT r.project AS project,
       r.suite_version AS suite_version,
       t.case_id AS case_id,
       count() AS trials,
       round(sum(t.seconds), 6) AS seconds,
       sum(t.input_tokens) AS input_tokens,
       sum(t.output_tokens) AS output_tokens
FROM trials AS t
INNER JOIN runs AS r USING (run_id)
WHERE t.error = ''
GROUP BY project, suite_version, case_id
ORDER BY project, suite_version, case_id;
