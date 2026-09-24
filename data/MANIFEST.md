# Where this corpus comes from

Committed run artifacts of two public repositories, copied verbatim. Nothing here was
produced by this project, and nothing was edited on the way in.

| Source | Commit | Copied |
| --- | --- | --- |
| [mcp-connector-testkit](https://github.com/Elletre/mcp-connector-testkit) | `53cac2ba40ce` | `evals/results/**/{trials.jsonl,summary.json}` |
| [agent-eval-lab](https://github.com/Elletre/agent-eval-lab) | `49749313b9d7` | `experiments/**/*.json`, `reports/*.json` |

Directory names flatten the original paths: `archive__2026-09-18-harness-v1__llama3-8b-baseline`
was `evals/results/archive/2026-09-18-harness-v1/llama3-8b-baseline`.

Both corpora include runs their own repositories keep as evidence of a mistake rather than as
results — a dataset that rewarded an agent for doing nothing, a harness that answered on the
connector's behalf, a wall clock that charged one policy for thinking longer. They are kept
here too: a suite's failures are part of what this project measures.

The two projects do not share a vocabulary. Their gates, families and per-trial fields differ,
so cross-project questions are asked per project and only then compared.
