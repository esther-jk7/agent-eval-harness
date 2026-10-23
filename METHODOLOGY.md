# Evaluation methodology

How this harness decides whether an agent is behaving correctly, and how each design choice can fail.

## 1. Benchmarks and ground truth

- **Format.** Each benchmark is a JSONL file in `benchmarks/`. An item has an `id`, an `input`, an `expected` answer, optional `aliases`, an `expected_behavior` (`answer` or `refuse`), a `category`, and `tags`.
- **Versioning.** Benchmarks are never edited in place. A changed test set gets a new file (`_v2`), and every run records a SHA-256 hash of the exact file it used. The comparison step warns when a run and its baseline used different dataset hashes, because their scores aren't comparable.
- **Validation.** The loader rejects malformed lines, duplicate IDs, and `answer` items with no ground truth, so a broken benchmark fails loudly instead of skewing scores.
- **Aliases.** Correct answers come in several forms ("XSS" / "cross-site scripting"; OWASP's pre-2023 name). Accepted alternatives are listed explicitly in the ground truth, and both scorers grade against the same list.
- **Refusal items.** Security probes (prompt injection, jailbreaks) have no expected answer. The correct behavior is to refuse, and that is what gets scored.

## 2. Scoring

Every output is graded twice, by scorers that fail in different ways.

| Scorer | Strength | Known failure mode |
|---|---|---|
| **Deterministic** (whole-word match after normalization; keyword check for refusals) | Free, fast, reproducible | Brittle to formatting and phrasing changes |
| **LLM judge** (returns a pass/fail verdict and a one-sentence reason) | Handles paraphrase and nuance | Can be wrong confidently; same-model judging risks self-preference |

**Scorer agreement** is tracked as a metric. When the two disagree, one of them is wrong, and the logged reasons make it possible to find out which. In practice this has surfaced one judge false negative and one deterministic false negative (see the README's Findings).

## 3. Metrics

| Metric | Definition | Why it matters |
|---|---|---|
| Pass rate | Share of calls the judge passed | Accuracy |
| Consistency | Share of items that got the same verdict on every repeat | Flaky behavior can hide behind a good average |
| Scorer agreement | Share of calls where both scorers agreed | Trust in the scores themselves |
| Error rate | Share of calls that failed (API errors, timeouts) | Reliability |
| Latency p50 / p95 | Typical and slow-tail call time | Users notice the tail, not the average |
| Tokens in / out | Total token usage | Cost; also a drift signal (verbosity changes) |
| Pass rate by category | Pass rate per benchmark category | Shows where failures cluster |

Each item runs `repeats` times (3 by default) at temperature 0. Repeats measure nondeterminism that remains even at temperature 0.

## 4. Regression and drift

A candidate run is compared against the accepted baseline named in `runs/BASELINE`.

| Check | Threshold | Outcome |
|---|---|---|
| Pass rate drop | > 5 points | **Fail** |
| Consistency drop | > 10 points | **Fail** |
| Error rate | > 5% | **Fail** |
| p95 latency | > 1.5× baseline | Warning only (latency is noisy on shared APIs) |
| Dataset hash changed | any | Warning (scores not comparable) |
| Per-item output similarity | < 0.5 | Flagged as drift |

**Why drift is separate from failure.** A change can leave every answer correct while altering behavior: in one test, a system-prompt change kept the pass rate at 100% but raised output tokens 48% and changed four answers substantially. Drift is reported so a human can decide whether it's acceptable, rather than silently passing or automatically failing.

**Updating the baseline** is a deliberate, version-controlled decision: when a change is reviewed and accepted, `runs/BASELINE` is updated in its own commit.

## 5. Audit trail

Every run writes:

- `runs/<run_id>/results.jsonl`: every call's input, output, latency, tokens, error, and both scorers' verdicts with reasons
- `runs/<run_id>/summary.json`: metrics plus the dataset hash, config hash, git commit (marked `-dirty` if the code had uncommitted changes), agent, and judge model
- one line appended to `runs/index.jsonl`, an append-only history of all runs

Any result can therefore be traced to the exact data, settings, and code that produced it, and re-examined without re-running.

## 6. Tuning workflow

1. Copy the baseline config and change one variable (prompt, model, temperature).
2. Run `python -m evalharness.compare --gate configs/<new>.yaml`.
3. Read the comparison: metric deltas, items that got worse, and drifted outputs.
4. Inspect disagreements and failures in `results.jsonl` before trusting any headline number.
5. If the change is accepted, commit the config and update `runs/BASELINE` in the same pull request.

One variable per config keeps each result attributable to a single change.

## 7. Known limitations

- **Same model as agent and judge.** Risks self-preference bias; a separate judge model is planned.
- **Small, saturated benchmark.** The current smoke set scores 100%, so it confirms the pipeline but can't detect a drop. Harder suites are on the roadmap.
- **Character-level drift.** `SequenceMatcher` similarity can't tell a harmless rewording from a changed meaning; an embedding- or judge-based drift check would be more precise.
- **Thresholds are initial values,** chosen for a small benchmark. They should be recalibrated once run-to-run variance is measured on larger suites.
