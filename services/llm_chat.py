"""
LLM text-chat wrapper — single point of text inference for the hub.

Supports BOTH Gemini and Claude. Defaults to Gemini (cheap).
When user adds Claude credits, set LLM_PROVIDER=claude and the hub auto-routes
all skill / smart-generate calls through Claude Sonnet for marketing-grade quality.

Routing:
  LLM_PROVIDER=gemini  (default) → Gemini 2.5 Flash/Pro
  LLM_PROVIDER=claude            → Claude Sonnet 4.5/Opus
  per-call provider= arg overrides the env default
"""
import json
import os

import requests

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
DEFAULT_PROVIDER = os.environ.get("LLM_PROVIDER", "gemini").lower().strip()

# Models (overridable via env)
GEMINI_TEXT_MODEL_FAST = os.environ.get("GEMINI_TEXT_MODEL_FAST", "gemini-2.5-flash")
GEMINI_TEXT_MODEL_SMART = os.environ.get("GEMINI_TEXT_MODEL_SMART", "gemini-2.5-pro")
CLAUDE_MODEL_FAST = os.environ.get("CLAUDE_MODEL_FAST", "claude-haiku-4-5-20251001")
CLAUDE_MODEL_SMART = os.environ.get("CLAUDE_MODEL_SMART", "claude-sonnet-4-6")

API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
CLAUDE_API = "https://api.anthropic.com/v1/messages"


def gemini_chat(
    system: str,
    user: str,
    max_tokens: int = 1024,
    temperature: float = 0.7,
    json_mode: bool = False,
    model: str | None = None,
    smart: bool = False,
    thinking_budget: int | None = None,
) -> str:
    """
    Single-turn chat. Returns the model's text output.

    Args:
        system: system instruction
        user: user message
        max_tokens: max output tokens (counts BOTH thinking + visible output for 2.5)
        temperature: sampling temperature
        json_mode: if True, forces JSON output (Gemini's responseMimeType)
        model: explicit model override
        smart: if True (and no model override), uses gemini-2.5-pro instead of flash
        thinking_budget: 0 = disabled (saves tokens for the actual reply),
                         -1 = dynamic auto-budget,
                         None = explicit default: 0 for fast model, dynamic for smart
                         For short replies always pass 0 — thinking eats reply tokens.

    Raises:
        RuntimeError on API failure or empty response
    """
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not set in environment")

    use_model = model or (GEMINI_TEXT_MODEL_SMART if smart else GEMINI_TEXT_MODEL_FAST)

    gen_config: dict = {
        "maxOutputTokens": max_tokens,
        "temperature": temperature,
    }
    if json_mode:
        gen_config["responseMimeType"] = "application/json"

    # Default: disable thinking on the fast model (it burns reply tokens for short outputs).
    # Smart model gets dynamic thinking since planning benefits from it.
    if thinking_budget is None:
        thinking_budget = -1 if smart else 0
    gen_config["thinkingConfig"] = {"thinkingBudget": thinking_budget}

    body: dict = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": gen_config,
    }

    url = f"{API_BASE}/{use_model}:generateContent?key={GEMINI_API_KEY}"

    try:
        resp = requests.post(url, json=body, timeout=120)
    except requests.RequestException as e:
        raise RuntimeError(f"Gemini request failed [model={use_model}]: {str(e)[:200]}")

    try:
        data = resp.json()
    except Exception:
        raise RuntimeError(f"Gemini non-JSON response [model={use_model}] status={resp.status_code}: {resp.text[:300]}")

    if "error" in data:
        msg = data["error"].get("message", str(data["error"]))
        raise RuntimeError(f"Gemini API error [model={use_model}]: {msg[:400]}")

    # Pull first candidate's text + check finish reason
    cands = data.get("candidates", []) or []
    if not cands:
        raise RuntimeError(f"Gemini returned no candidates [model={use_model}]")

    first = cands[0]
    finish = first.get("finishReason", "")
    parts = (first.get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts).strip()

    if not text:
        raise RuntimeError(f"Gemini returned no text [model={use_model}]. finishReason={finish}")

    # Warn (via raised hint) only if truncated AND clearly cut off mid-sentence
    if finish == "MAX_TOKENS":
        # Caller may want to retry with higher budget; we still return what we got
        # but signal it via a sentinel comment for debugging downstream.
        pass

    return text


def gemini_chat_json(
    system: str,
    user: str,
    max_tokens: int = 2048,
    smart: bool = False,
    model: str | None = None,
) -> dict:
    """
    Same as gemini_chat but parses the response as JSON.
    Uses Gemini's responseMimeType=application/json for clean output (no markdown fences).
    """
    raw = gemini_chat(
        system=system,
        user=user,
        max_tokens=max_tokens,
        temperature=0.5,
        json_mode=True,
        smart=smart,
        model=model,
    )
    # Gemini in JSON mode returns pure JSON, but defensively strip any fences
    text = raw.strip()
    if text.startswith("```"):
        first = text.find("\n")
        if first > 0:
            text = text[first + 1:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Gemini JSON parse failed: {str(e)[:150]}. Raw: {text[:250]}")


# ─── Claude (Anthropic) ─────────────────────────────────────────────────────

def claude_chat(
    system: str,
    user: str,
    max_tokens: int = 1024,
    temperature: float = 0.7,
    model: str | None = None,
    smart: bool = False,
) -> str:
    """Single-turn Claude chat via the Anthropic REST API. Returns text output."""
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY not set — add Claude credits + set the env var")

    use_model = model or (CLAUDE_MODEL_SMART if smart else CLAUDE_MODEL_FAST)
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": use_model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    try:
        resp = requests.post(CLAUDE_API, json=body, headers=headers, timeout=120)
    except requests.RequestException as e:
        raise RuntimeError(f"Claude request failed [model={use_model}]: {str(e)[:200]}")

    try:
        data = resp.json()
    except Exception:
        raise RuntimeError(f"Claude non-JSON response [model={use_model}] status={resp.status_code}: {resp.text[:300]}")

    if data.get("type") == "error" or "error" in data:
        err = data.get("error") or data
        msg = err.get("message") if isinstance(err, dict) else str(err)
        raise RuntimeError(f"Claude API error [model={use_model}]: {str(msg)[:400]}")

    parts = data.get("content") or []
    text = "".join(p.get("text", "") for p in parts if p.get("type") == "text").strip()
    if not text:
        raise RuntimeError(f"Claude returned no text [model={use_model}]. stop_reason={data.get('stop_reason','?')}")
    return text


def claude_chat_json(
    system: str,
    user: str,
    max_tokens: int = 2048,
    smart: bool = False,
    model: str | None = None,
) -> dict:
    """Claude chat that parses output as JSON. Strips markdown fences if present."""
    sys_with_json = system + "\n\nIMPORTANT: Return ONLY valid JSON. No markdown fences, no preamble."
    raw = claude_chat(system=sys_with_json, user=user, max_tokens=max_tokens, temperature=0.5, smart=smart, model=model).strip()
    if raw.startswith("```"):
        first = raw.find("\n")
        if first > 0:
            raw = raw[first + 1:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Claude JSON parse failed: {str(e)[:150]}. Raw: {raw[:250]}")


# ─── Unified router ─────────────────────────────────────────────────────────

def chat(system: str, user: str, smart: bool = False, provider: str | None = None, **kwargs) -> str:
    """
    Provider-agnostic chat. Routes to Gemini or Claude based on:
      - explicit `provider` arg (per-call override)
      - LLM_PROVIDER env var (global default)
      - falls back to 'gemini' if neither set
    """
    p = (provider or DEFAULT_PROVIDER).lower().strip()
    if p == "claude":
        if not ANTHROPIC_API_KEY:
            # Graceful fallback to Gemini if Claude isn't configured
            print("[llm_chat] LLM_PROVIDER=claude but ANTHROPIC_API_KEY missing — falling back to Gemini")
            return gemini_chat(system=system, user=user, smart=smart, **kwargs)
        return claude_chat(system=system, user=user, smart=smart, **kwargs)
    return gemini_chat(system=system, user=user, smart=smart, **kwargs)


def chat_json(system: str, user: str, smart: bool = False, provider: str | None = None, **kwargs) -> dict:
    """Provider-agnostic JSON chat. Same routing as chat()."""
    p = (provider or DEFAULT_PROVIDER).lower().strip()
    if p == "claude":
        if not ANTHROPIC_API_KEY:
            print("[llm_chat] LLM_PROVIDER=claude but ANTHROPIC_API_KEY missing — falling back to Gemini")
            return gemini_chat_json(system=system, user=user, smart=smart, **kwargs)
        return claude_chat_json(system=system, user=user, smart=smart, **kwargs)
    return gemini_chat_json(system=system, user=user, smart=smart, **kwargs)
