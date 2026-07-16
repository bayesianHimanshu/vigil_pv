"""Thin structured-generation interface.

This is the ONLY place that knows about the Gemini/Vertex SDK. Agents call
`StructuredLLM.generate(...)` with a Pydantic schema and get back a parsed
instance plus call metadata for the audit trail. Swapping providers means
reimplementing this one class - the agent logic above it stays portable.
"""

from __future__ import annotations
import time
from dataclasses import dataclass
from typing import Type, Tuple
from pydantic import BaseModel


@dataclass
class LLMMeta:
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int


class StructuredLLM:
    def __init__(self, client, model: str):
        self._client = client
        self.model = model

    def generate(
        self,
        *,
        system: str,
        user: str,
        schema: Type[BaseModel],
        temperature: float = 0.0,
    ) -> Tuple[BaseModel, LLMMeta]:
        from google.genai import types

        t0 = time.monotonic()
        resp = self._client.models.generate_content(
            model=self.model,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                response_mime_type="application/json",
                response_schema=schema,  # Pydantic model -> enforced structure
                temperature=temperature,
            ),
        )
        latency_ms = int((time.monotonic() - t0) * 1000)
        parsed = resp.parsed  # validated instance of `schema`
        if parsed is None:
            # Fallback: parse text if the SDK did not populate `.parsed`
            parsed = schema.model_validate_json(resp.text)
        um = getattr(resp, "usage_metadata", None)
        meta = LLMMeta(
            model=self.model,
            input_tokens=getattr(um, "prompt_token_count", 0) or 0,
            output_tokens=getattr(um, "candidates_token_count", 0) or 0,
            latency_ms=latency_ms,
        )
        return parsed, meta
