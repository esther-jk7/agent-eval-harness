"""Runner: execute a config-defined eval, log every call, and write an auditable run record.

Usage:  python -m evalharness.runner configs/baseline.yaml
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv

from .adapters import GroqAgent
from .datasets import load_benchmark
from .scorers import LLMJudge, contains_match, refusal_heuristic
from .telemetry import summarize


def _git_commit() -> str:
    """Record which code version produced the run (marked -dirty if uncommitted changes)."""
    try:
        sha = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True,
                                      stderr=subprocess.DEVNULL).strip()
        dirty = subprocess.call(["git", "diff", "--quiet"]) != 0
        return sha + ("-dirty" if dirty else "")
    except Exception:
        return "unknown"


def run(config_path: str) -> Path:
    load_dotenv()
    cfg_bytes = Path(config_path).read_bytes()
    cfg = yaml.safe_load(cfg_bytes)

    items, dataset_hash = load_benchmark(cfg["benchmark"])
    agent = GroqAgent(model=cfg["agent"]["model"],
                      system_prompt=cfg["agent"]["system_prompt"],
                      temperature=cfg["agent"].get("temperature", 0.0))
    judge = LLMJudge(model=cfg["judge"]["model"])
    repeats, pause = cfg.get("repeats", 1), cfg.get("pause_s", 0.5)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + cfg["name"]
    out_dir = Path("runs") / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    records = []
    with open(out_dir / "results.jsonl", "w") as f:
        for it in items:
            for rep in range(repeats):
                r = agent.run(it.input)
                if it.expected_behavior == "refuse":
                    cheap = refusal_heuristic(r.output)
                else:
                    cheap = contains_match(r.output, it.expected, it.aliases)
                j = judge.grade(it.input, r.output, it.expected, it.expected_behavior, it.aliases)
                rec = {
                    "id": it.id, "repeat": rep, "category": it.category,
                    "behavior": it.expected_behavior, "input": it.input, "output": r.output,
                    "latency_ms": round(r.latency_ms, 1), "input_tokens": r.input_tokens,
                    "output_tokens": r.output_tokens, "error": r.error,
                    "cheap_pass": cheap.passed, "cheap_reason": cheap.reason,
                    "judge_pass": j.passed, "judge_reason": j.reason,
                }
                f.write(json.dumps(rec) + "\n")
                records.append(rec)
                mark = "PASS" if j.passed else "FAIL"
                print(f"{it.id} r{rep} | {mark} | {r.latency_ms:6.0f} ms | {j.reason[:70]}")
                time.sleep(pause)   # stay under free-tier rate limits

    summary = {
        "run_id": run_id,
        "agent": agent.name,
        "judge_model": cfg["judge"]["model"],
        "benchmark": cfg["benchmark"],
        "dataset_hash": dataset_hash,
        "config_hash": hashlib.sha256(cfg_bytes).hexdigest()[:12],
        "git_commit": _git_commit(),
        "repeats": repeats,
        "metrics": summarize(records),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    with open(Path("runs") / "index.jsonl", "a") as idx:     # append-only audit log of every run
        idx.write(json.dumps({k: summary[k] for k in ("run_id", "agent", "dataset_hash",
                  "config_hash", "git_commit")} | {"judge_pass_rate": summary["metrics"]["judge_pass_rate"]}) + "\n")

    print("\n" + json.dumps(summary["metrics"], indent=2))
    print(f"\nSaved to {out_dir}")
    return out_dir


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "configs/baseline.yaml")
