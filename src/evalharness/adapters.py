"""Adapters: one common interface so any agent can be evaluated the same way."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Callable, Protocol


@dataclass
class AgentResponse:
    """Everything we capture from a single agent call."""
    output: str
    latency_ms: float
    input_tokens: int = 0
    output_tokens: int = 0
    error: str | None = None
    metadata: dict = field(default_factory=dict)


class Agent(Protocol):
    """Any agent the harness can evaluate: it has a name and a run() method."""
    name: str

    def run(self, prompt: str) -> AgentResponse: ...


class GroqAgent:
    """Wraps a Groq-hosted LLM so it can be evaluated like any other agent."""

    def __init__(self, model: str = "openai/gpt-oss-120b",
                 system_prompt: str = "You are a helpful assistant. Answer concisely.",
                 temperature: float = 0.0):
        from groq import Groq
        self.client = Groq(api_key=os.environ["GROQ_API_KEY"])
        self.model = model
        self.system_prompt = system_prompt
        self.temperature = temperature
        self.name = f"groq:{model}"

    def run(self, prompt: str) -> AgentResponse:
        start = time.perf_counter()
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                messages=[{"role": "system", "content": self.system_prompt},
                          {"role": "user", "content": prompt}],
            )
            usage = resp.usage
            return AgentResponse(
                output=resp.choices[0].message.content or "",
                latency_ms=(time.perf_counter() - start) * 1000,
                input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                output_tokens=getattr(usage, "completion_tokens", 0) or 0,
            )
        except Exception as e:  # record failures instead of crashing the run
            return AgentResponse(output="", latency_ms=(time.perf_counter() - start) * 1000,
                                 error=f"{type(e).__name__}: {e}")


class CallableAgent:
    """Wraps any Python function (e.g. an existing RAG pipeline) as an agent."""

    def __init__(self, fn: Callable[[str], str], name: str):
        self.fn = fn
        self.name = name

    def run(self, prompt: str) -> AgentResponse:
        start = time.perf_counter()
        try:
            out = self.fn(prompt)
            return AgentResponse(output=str(out), latency_ms=(time.perf_counter() - start) * 1000)
        except Exception as e:
            return AgentResponse(output="", latency_ms=(time.perf_counter() - start) * 1000,
                                 error=f"{type(e).__name__}: {e}")
