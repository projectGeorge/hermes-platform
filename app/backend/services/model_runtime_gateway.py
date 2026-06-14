"""Provider-aware model runtime gateway for local LM Studio and cloud LLM."""

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

import httpx

from app.backend.core.settings import Settings


@dataclass(frozen=True)
class RuntimeProvenance:
    provider: str
    model_name: str
    runtime_profile: str


@dataclass(frozen=True)
class CompletionResult:
    content: dict[str, Any]
    provenance: RuntimeProvenance
    raw_text: str


def resolve_profile_config(settings: Settings, profile: str) -> dict[str, Any]:
    if profile == "ingestion":
        return {
            "provider": settings.ingestion_model_provider,
            "model_name": settings.ingestion_model_name,
            "base_url": settings.lm_studio_base_url,
            "timeout_seconds": settings.ingestion_model_timeout_seconds,
            "temperature": 0.3,
            "max_tokens": 1024,
        }
    elif profile == "local_agent":
        return {
            "provider": settings.local_agent_model_provider,
            "model_name": settings.local_agent_model_name,
            "base_url": settings.lm_studio_base_url,
            "timeout_seconds": settings.local_agent_model_timeout_seconds,
            "temperature": settings.local_agent_model_temperature,
            "max_tokens": settings.local_agent_model_max_tokens,
        }
    elif profile == "reasoning":
        return {
            "provider": settings.reasoning_model_provider,
            "model_name": settings.reasoning_model_name,
            "base_url": settings.reasoning_model_base_url,
            "timeout_seconds": settings.reasoning_model_timeout_seconds,
            "temperature": settings.reasoning_model_temperature,
            "max_tokens": settings.reasoning_model_max_tokens,
            "api_key": settings.reasoning_model_api_key,
        }
    elif profile == "reasoning_json":
        return {
            "provider": settings.reasoning_model_provider,
            "model_name": settings.reasoning_model_name,
            "base_url": settings.reasoning_model_base_url,
            "timeout_seconds": settings.reasoning_model_timeout_seconds,
            "temperature": 0,
            "max_tokens": max(settings.reasoning_model_max_tokens, 2048),
            "api_key": settings.reasoning_model_api_key,
        }
    else:
        raise ValueError(f"Unknown runtime profile: {profile}")


def _is_cloud_provider(config: dict[str, Any]) -> bool:
    return config["provider"] not in ("lm_studio", "")


def _build_headers(config: dict[str, Any]) -> dict[str, str]:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    api_key = config.get("api_key")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _extract_json_payload(raw: str) -> str:
    stripped = raw.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            stripped = "\n".join(lines[1:-1]).strip()
            if stripped.lower().startswith("json"):
                stripped = stripped[4:].lstrip()

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and start < end:
        return stripped[start:end + 1]

    return stripped


def _extract_choice_content(data: dict[str, Any]) -> str:
    choice = data.get("choices", [{}])[0]
    message = choice.get("message", {}) if isinstance(choice, dict) else {}
    content = message.get("content")
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text" and isinstance(item.get("text"), str):
                text_parts.append(item["text"])
                continue
            if isinstance(item.get("content"), str):
                text_parts.append(item["content"])
        if text_parts:
            return "\n".join(text_parts)

    tool_calls = message.get("tool_calls")
    if isinstance(tool_calls, list):
        for tool_call in tool_calls:
            if not isinstance(tool_call, dict):
                continue
            function = tool_call.get("function")
            if isinstance(function, dict) and isinstance(function.get("arguments"), str):
                return function["arguments"]

    reasoning = message.get("reasoning")
    if isinstance(reasoning, str):
        return reasoning

    return ""


async def structured_completion(
    *,
    settings: Settings,
    messages: list[dict[str, str]],
    profile: str,
) -> CompletionResult:
    config = resolve_profile_config(settings, profile)

    if not config["model_name"]:
        raise ValueError(
            f"Model is not configured for profile '{profile}'. Set the appropriate environment variable."
        )

    headers = _build_headers(config)
    timeout = httpx.Timeout(float(config["timeout_seconds"]))

    payload: dict[str, Any] = {
        "model": config["model_name"],
        "messages": messages,
        "temperature": config["temperature"],
        "max_tokens": config["max_tokens"],
        "stream": False,
    }

    if _is_cloud_provider(config):
        payload["response_format"] = {"type": "json_object"}

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{config['base_url']}/chat/completions",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
    except httpx.TimeoutException:
        raise RuntimeError("Model runtime request timed out")
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"Model runtime error (HTTP {e.response.status_code})") from e
    except httpx.RequestError as e:
        raise RuntimeError(f"Model runtime error: {e}") from e

    raw = _extract_choice_content(data)

    import json as _json

    try:
        parsed = _json.loads(_extract_json_payload(raw))
    except _json.JSONDecodeError:
        raise RuntimeError("Failed to parse model response as JSON")

    provenance = RuntimeProvenance(
        provider=config["provider"],
        model_name=config["model_name"],
        runtime_profile=profile,
    )

    return CompletionResult(
        content=parsed,
        provenance=provenance,
        raw_text=raw,
    )


async def stream_completion(
    *,
    settings: Settings,
    messages: list[dict[str, str]],
    profile: str,
) -> AsyncGenerator[str, None]:
    config = resolve_profile_config(settings, profile)

    if not config["model_name"]:
        yield f"Model is not configured for profile '{profile}'. Set the appropriate environment variable."
        return

    headers = _build_headers(config)
    timeout = httpx.Timeout(float(config["timeout_seconds"]))

    payload = {
        "model": config["model_name"],
        "messages": messages,
        "temperature": config["temperature"],
        "max_tokens": config["max_tokens"],
        "stream": True,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                f"{config['base_url']}/chat/completions",
                json=payload,
                headers=headers,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_line = line[6:]
                        if data_line.strip() == "[DONE]":
                            return
                        try:
                            import json as _json

                            chunk = _json.loads(data_line)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content")
                            if content:
                                yield content
                        except (_json.JSONDecodeError, IndexError, KeyError):
                            continue
    except httpx.TimeoutException:
        yield "Model runtime request timed out."
    except httpx.HTTPStatusError as e:
        yield f"Model runtime error (HTTP {e.response.status_code})."
    except httpx.RequestError as e:
        yield f"Model runtime error: {e}."
