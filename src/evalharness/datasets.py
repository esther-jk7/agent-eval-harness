"""Benchmark datasets: load, validate, and fingerprint versioned JSONL test sets."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class BenchmarkItem(BaseModel):
    """One test case with its ground truth."""
    id: str
    input: str
    expected: str | None = None                      # ground-truth answer, if any
    aliases: list[str] = Field(default_factory=list) # other accepted answers
    expected_behavior: Literal["answer", "refuse"] = "answer"
    category: str = "general"
    tags: list[str] = Field(default_factory=list)


def load_benchmark(path: str | Path) -> tuple[list[BenchmarkItem], str]:
    """Load a JSONL benchmark. Returns the items and a SHA-256 hash of the file,
    so every run records exactly which dataset version it was scored against."""
    path = Path(path)
    raw = path.read_bytes()
    items, seen = [], set()
    for n, line in enumerate(raw.decode().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = BenchmarkItem(**json.loads(line))
        except Exception as e:
            raise ValueError(f"{path.name} line {n}: {e}") from e
        if item.id in seen:
            raise ValueError(f"{path.name} line {n}: duplicate id '{item.id}'")
        if item.expected_behavior == "answer" and not item.expected:
            raise ValueError(f"{path.name} line {n}: 'answer' items need an expected value")
        seen.add(item.id)
        items.append(item)
    return items, hashlib.sha256(raw).hexdigest()[:12]
