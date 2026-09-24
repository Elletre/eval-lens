-- Which cases ever separated the two sides of a comparison, and which never did.
-- The view behind this is in schema.sql; the questions below build on it.
SELECT project, suite_version, case_id, family, comparisons, discriminated, label,
       round(seconds, 6) AS seconds
FROM case_verdicts
ORDER BY project, suite_version, case_id;
