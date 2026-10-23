"""Regression and drift detection: compare a candidate run against an accepted baseline.

Compare two runs:     python -m evalharness.compare runs/<baseline> runs/<candidate>
CI gate (run+check):  python -m evalharness.compare --gate configs/baseline.yaml
Exit code 1 means a regression was detected.
"""
from __future__ import annotations

import json
import sys
from difflib import SequenceMatcher
from pathlib import Path

# Thresholds: how much change counts as a regression.
MAX_PASS_RATE_DROP = 0.05       # judge pass rate may drop at most 5 points
MAX_CONSISTENCY_DROP = 0.10     # consistency may drop at most 10 points
MAX_ERROR_RATE = 0.05           # more than 5% failed calls is a regression
LATENCY_WARN_RATIO = 1.5        # p95 latency 1.5x baseline -> warning (noisy, so not a failure)
DRIFT_SIMILARITY = 0.5          # outputs less than 50% similar to baseline -> flagged as drifted
BASELINE_POINTER = Path("runs/BASELINE")


def _load(run_dir: Path) -> tuple[dict, dict[str, list[dict]]]:
    summary = json.loads((run_dir / "summary.json").read_text())
    by_id: dict[str, list[dict]] = {}
    for line in (run_dir / "results.jsonl").read_text().splitlines():
        rec = json.loads(line)
        by_id.setdefault(rec["id"], []).append(rec)
    return summary, by_id


def compare(base_dir: Path, cand_dir: Path) -> tuple[bool, str]:
    """Return (regressed, markdown report)."""
    bs, br = _load(base_dir)
    cs, cr = _load(cand_dir)
    bm, cm = bs["metrics"], cs["metrics"]
    failures, warnings, lines = [], [], []

    def delta(key):
        return cm[key] - bm[key]

    if delta("judge_pass_rate") < -MAX_PASS_RATE_DROP:
        failures.append(f"Pass rate dropped {bm['judge_pass_rate']:.0%} -> {cm['judge_pass_rate']:.0%}")
    if delta("consistency_rate") < -MAX_CONSISTENCY_DROP:
        failures.append(f"Consistency dropped {bm['consistency_rate']:.0%} -> {cm['consistency_rate']:.0%}")
    if cm["error_rate"] > MAX_ERROR_RATE:
        failures.append(f"Error rate {cm['error_rate']:.0%} exceeds {MAX_ERROR_RATE:.0%}")
    if bm["latency_p95_ms"] and cm["latency_p95_ms"] > LATENCY_WARN_RATIO * bm["latency_p95_ms"]:
        warnings.append(f"p95 latency {bm['latency_p95_ms']:.0f} -> {cm['latency_p95_ms']:.0f} ms")
    if bs["dataset_hash"] != cs["dataset_hash"]:
        warnings.append("Benchmark changed since baseline: scores are not directly comparable")

    # Per-item flips and output drift
    flips, drifted = [], []
    for item_id, cand_recs in cr.items():
        base_recs = br.get(item_id)
        if not base_recs:
            continue
        b_pass = sum(r["judge_pass"] for r in base_recs) / len(base_recs)
        c_pass = sum(r["judge_pass"] for r in cand_recs) / len(cand_recs)
        if c_pass < b_pass:
            flips.append(f"{item_id}: {b_pass:.0%} -> {c_pass:.0%} ({cand_recs[0]['judge_reason'][:80]})")
        sim = SequenceMatcher(None, base_recs[0]["output"], cand_recs[0]["output"]).ratio()
        if sim < DRIFT_SIMILARITY:
            drifted.append(f"{item_id}: similarity {sim:.2f}")

    lines.append(f"## Eval comparison\n\nBaseline: `{bs['run_id']}` ({bs['git_commit']})  \n"
                 f"Candidate: `{cs['run_id']}` ({cs['git_commit']})\n")
    lines.append("| Metric | Baseline | Candidate | Change |\n|---|---|---|---|")
    for k in ("judge_pass_rate", "consistency_rate", "scorer_agreement", "error_rate",
              "latency_p50_ms", "latency_p95_ms", "tokens_out_total"):
        lines.append(f"| {k} | {bm[k]} | {cm[k]} | {cm[k] - bm[k]:+.4g} |")
    for title, items in (("Regressions", failures), ("Warnings", warnings),
                         ("Items that got worse", flips), ("Output drift", drifted)):
        if items:
            lines.append(f"\n**{title}**\n" + "\n".join(f"- {x}" for x in items))
    regressed = bool(failures)
    lines.append(f"\n**Result: {'REGRESSION - fail' if regressed else 'PASS'}**")
    return regressed, "\n".join(lines)


def gate(config_path: str) -> int:
    """Run a fresh eval and compare it against the accepted baseline. For CI."""
    from .runner import run
    cand = run(config_path)
    base = Path(BASELINE_POINTER.read_text().strip())
    regressed, report = compare(base, cand)
    (cand / "comparison.md").write_text(report)
    print("\n" + report)
    return 1 if regressed else 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["--gate"]:
        sys.exit(gate(args[1] if len(args) > 1 else "configs/baseline.yaml"))
    regressed, report = compare(Path(args[0]), Path(args[1]))
    print(report)
    sys.exit(1 if regressed else 0)
