# Method: what is measured, and what each word means

Every number in [`REPORT.md`](../REPORT.md) comes from one of the definitions below, applied
to runs that two other repositories had already recorded and published. Nothing here was
produced for this project: the corpus is copied verbatim, and where it came from is written
in [`data/MANIFEST.md`](../data/MANIFEST.md).

## The units

**Trial** — one attempt at one case: `(run_id, case_id, repeat)`. It carries a verdict, the
labels of what failed, the tools it called, its tokens and its seconds.

**Run** — one execution of one suite under one configuration: project, dataset and its
version, variant, model, configuration, date. A *variant* is the thing under test — a seeded
connector defect, a prompt policy, an oracle-driven fixture.

**Case** — a scenario in the dataset. Cases only mean the same thing inside one project and
one dataset version, so every question is asked inside that scope and only then compared.

**Comparison** — a pair of runs that share project, dataset version, model and configuration
and differ in exactly one variant. The configuration fingerprint is where the sampling
temperature, the wall clock, the harness version and the scorer version live, and holding it
constant is not pedantry here: in this corpus the wall clock alone moved one published
conclusion and the harness version moved another.

**A/A pair** — two runs of the *same* variant under the same configuration. Not a comparison:
it is the control, and whatever it reports is the instrument talking to itself.

**Trials the harness cut short** — a wall clock or token limit ended the attempt, so there is
no verdict about the model. They are excluded from every rate. Counting them as failures is a
mistake one of the source projects made, found and fixed; the corpus keeps both runs.

## The measurements

### 1. Case information

Inside one comparison, a case **discriminates** when its pass rate differs between the two
sides. Over the whole corpus a case is:

| Label | Meaning |
| --- | --- |
| `informative` | discriminated in at least one comparison |
| `saturated` | never discriminated, and always passed |
| `floored` | never discriminated, and always failed |
| `quiet` | never discriminated, but its verdicts are not constant — dispersion without an answer |

A case that took part in no comparison is *never compared* and gets no verdict rather than a
flattering one.

This is deliberately the weakest possible criterion: one difference, in one comparison, in
one direction. It was chosen before the pruning experiment was run, and the A/A pair
measures what it costs — how many cases it flags when there is provably nothing to find.

### 2. Repeat noise

Among cases run more than once inside a single run, the share whose repeats disagree. Nothing
changed between those repeats except sampling, so this is the instrument's own dispersion,
and a difference smaller than it cannot be resolved by adding more comparisons of the same
kind.

### 3. Drift

The same variant and dataset scored in more than one run, reported as the spread between the
highest and lowest pass rate. Where the configuration also changed, the change is named:
drift here is the joint effect of a setting nobody thought was load-bearing and the sampling
nobody pinned.

### 4. The A/A pair

The A/A pair is scored exactly as a comparison is scored: the mean per-case difference, the
exact sign test over the cases that moved, and the number of cases the informativeness
criterion would flag. The expected answers are zero, one and zero. The distance from those is
the false-positive rate of everything above.

### 5. Cost, and the cost of silence

Seconds and tokens per trial, summed per case and per dataset version, then split by what the
case was worth: time spent on informative cases against time spent on silent ones. Local
models cost no money, so no money is reported. A dollar figure for a hosted model would be a
multiplication, not a measurement.

### 6. Variance

A crude decomposition of the binary verdicts of one comparison into what varies between
cases, what varies between the two variants, and a residual. On twenty-seven cases this is
shaky, and it is reported as a direction rather than a measurement: the residual absorbs
everything the other two terms cannot explain. No conclusion in the report rests on it.

### 7. Failures and silent gates

How often each failure label appears, and which gates are recorded on every trial and have
never once failed. A gate that cannot fail is not a check: either nothing in the suite breaks
that rule, or the rule is written so that nothing can. Neither is visible from a pass rate.

Where a project records named gates, its own names are kept. Where it records free text, the
text is mapped to a small label table in
[`ingest/mcpqa.py`](../src/eval_lens/ingest/mcpqa.py); the mapping is data, not inference,
and anything unmatched keeps its original wording.

### 8. The pruning experiment

The falsifiable claim, fixed in the plan before any of it was computed:

> Remove the cases with no discriminating power and the published conclusions do not change,
> while the suite gets materially shorter.

Each comparison is recomputed on the cases that **other** comparisons found informative —
never on the ones it decided itself. Judging a case by the comparison it is then used to
re-decide would make the answer true by construction. For each comparison the report gives
the effect on the full suite and on the pruned one, the exact sign test on both, and the
share of running time removed. A comparison *survives* when its verdict at 5% is the same on
both.

The outcome is published either way. A pruning that changes a conclusion would mean the
criterion is wrong, which is worth as much as a pruning that does not.

## The statistics

- **Exact sign test**, two-sided, over cases whose pass rate moved between the two sides. It
  is the test both source projects already used for their published comparisons, so the
  recomputed numbers are comparable with the originals.
- **No confidence intervals on the metrics themselves.** An interval on "35% of cases
  disagree with their own repeats" would need repeats of the whole run, which this corpus does
  not have. The A/A pair is the one place where a null distribution exists at all.
- **Two implementations.** Every metric is computed twice — in Python on normalised rows, and
  in ClickHouse SQL in [`sql/`](../sql) — and a test holds the two equal. It is both a check
  and the demonstration: a query nobody verified is an instrument nobody calibrated.
