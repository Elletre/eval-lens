-- Which failures actually happen, and in how many different runs.
SELECT r.project AS project,
       label,
       count() AS trials,
       uniqExact(t.run_id) AS runs
FROM trials AS t
INNER JOIN runs AS r USING (run_id)
ARRAY JOIN arrayDistinct(t.failures) AS label
WHERE t.error = ''
GROUP BY project, label
ORDER BY trials DESC, project, label;
