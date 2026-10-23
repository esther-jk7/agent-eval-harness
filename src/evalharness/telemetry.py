"""Telemetry: turn per-call records into latency, token, error, and quality metrics."""
from __future__ import annotations

import numpy as np
import pandas as pd


def summarize(records: list[dict]) -> dict:
    """Aggregate per-call records from a run into one metrics dict."""
    df = pd.DataFrame(records)
    ok = df[df["error"].isna()]
    lat = ok["latency_ms"].to_numpy() if len(ok) else np.array([0.0])

    # Consistency: an item is consistent if every repeat got the same judge verdict.
    per_item = df.groupby("id")["judge_pass"].agg(lambda s: s.nunique() == 1)

    metrics = {
        "n_items": int(df["id"].nunique()),
        "n_calls": int(len(df)),
        "judge_pass_rate": round(float(df["judge_pass"].mean()), 4),
        "cheap_pass_rate": round(float(df["cheap_pass"].mean()), 4),
        "scorer_agreement": round(float((df["judge_pass"] == df["cheap_pass"]).mean()), 4),
        "consistency_rate": round(float(per_item.mean()), 4),
        "error_rate": round(float(df["error"].notna().mean()), 4),
        "latency_p50_ms": round(float(np.percentile(lat, 50)), 1),
        "latency_p95_ms": round(float(np.percentile(lat, 95)), 1),
        "tokens_in_total": int(df["input_tokens"].sum()),
        "tokens_out_total": int(df["output_tokens"].sum()),
    }
    by_cat = df.groupby("category")["judge_pass"].mean().round(4)
    metrics["judge_pass_rate_by_category"] = {k: float(v) for k, v in by_cat.items()}
    return metrics
