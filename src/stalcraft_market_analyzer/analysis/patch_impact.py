from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


PatchImpact = Literal["BUFF", "NERF", "NEUTRAL"]
Severity = Literal["critical", "high", "medium", "low"]


class PatchImpactStructured(BaseModel):
    severity: Severity = Field(default="medium")
    impact: PatchImpact = Field(default="NEUTRAL")
    buffed_items: list[str] = Field(default_factory=list)
    nerfed_items: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    notes: str = Field(default="")


@dataclass(frozen=True, slots=True)
class PatchImpactLLMConfig:
    enabled: bool
    model: str


def load_patch_llm_config_from_env() -> PatchImpactLLMConfig:
    enabled = os.environ.get("PATCH_IMPACT_LLM_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
    model = os.environ.get("PATCH_IMPACT_LLM_MODEL", "gpt-5.2-mini").strip()
    return PatchImpactLLMConfig(enabled=enabled, model=model)


def analyze_patch_notes(*, patch_version: str, patch_text: str) -> dict[str, Any]:
    """
    LLM-assisted patch impact classifier.

    MVP behavior:
    - If disabled or key missing => deterministic stub (still valid JSON shape via pydantic).
    - If enabled => call OpenAI Responses API JSON mode (best-effort).
    """
    cfg = load_patch_llm_config_from_env()
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()

    if not cfg.enabled:
        stub = PatchImpactStructured(
            severity="low",
            impact="NEUTRAL",
            buffed_items=[],
            nerfed_items=[],
            confidence=0.0,
            notes="PATCH_IMPACT_LLM_ENABLED=false (stub mode). Enable + set OPENAI_API_KEY for real LLM classification.",
        )
        return {"patch_version": patch_version, "source": "stub", **stub.model_dump()}

    if not api_key:
        stub = PatchImpactStructured(
            severity="medium",
            impact="NEUTRAL",
            buffed_items=[],
            nerfed_items=[],
            confidence=0.0,
            notes="OPENAI_API_KEY missing (refusing remote call).",
        )
        return {"patch_version": patch_version, "source": "stub_missing_key", **stub.model_dump()}

    structured = _openai_patch_impact(patch_version=patch_version, patch_text=patch_text, model=cfg.model)
    return {"patch_version": patch_version, "source": f"openai:{cfg.model}", **structured.model_dump()}


def _openai_patch_impact(*, patch_version: str, patch_text: str, model: str) -> PatchImpactStructured:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    url = "https://api.openai.com/v1/chat/completions"
    system = (
        "You classify Stalcraft-style patch notes for market relevance. "
        "Return STRICT JSON matching the schema with keys: "
        "severity (critical|high|medium|low), impact (BUFF|NERF|NEUTRAL), buffed_items (array of strings), "
        "nerfed_items (array of strings), confidence (0..1), notes (short string)."
    )
    user = f"PATCH_VERSION={patch_version}\n\nPATCH_NOTES:\n{patch_text}"

    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        logger.warning("OpenAI patch impact call failed: %s", error)
        return PatchImpactStructured(
            severity="medium",
            impact="NEUTRAL",
            buffed_items=[],
            nerfed_items=[],
            confidence=0.0,
            notes=f"OpenAI call failed ({type(error).__name__}).",
        )

    text = _extract_openai_chat_text(raw)
    if not text.strip():
        return PatchImpactStructured(
            severity="medium",
            impact="NEUTRAL",
            buffed_items=[],
            nerfed_items=[],
            confidence=0.0,
            notes="Empty model output.",
        )

    try:
        data_obj = json.loads(text)
        if not isinstance(data_obj, dict):
            raise ValueError("not-object")
        return PatchImpactStructured.model_validate(data_obj)
    except Exception as error:
        logger.warning("Failed to validate LLM JSON: %s", error)
        return PatchImpactStructured(
            severity="medium",
            impact="NEUTRAL",
            buffed_items=[],
            nerfed_items=[],
            confidence=0.0,
            notes="Invalid JSON returned by model.",
        )


def _extract_openai_chat_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        choice0 = choices[0]
        if isinstance(choice0, dict):
            message = choice0.get("message")
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                return message["content"]
    return ""
