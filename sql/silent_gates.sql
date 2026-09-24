-- Gates a project records on every trial and that have never once failed.
SELECT r.project AS project,
       gate,
       count() AS trials
FROM trials AS t
INNER JOIN runs AS r USING (run_id)
ARRAY JOIN mapKeys(t.gates) AS gate, mapValues(t.gates) AS passed
WHERE t.error = ''
GROUP BY project, gate
HAVING sum(passed = 0) = 0
ORDER BY project, gate;
