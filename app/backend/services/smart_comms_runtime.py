"""Smart Comms runtime for contextual chat."""

from collections.abc import AsyncGenerator

from app.backend.core.settings import get_settings
from app.backend.services.model_runtime_gateway import stream_completion, resolve_profile_config


async def stream_chat_response(
    messages: list[dict[str, str]],
) -> AsyncGenerator[str, None]:
    """Stream a chat response from the cloud reasoning model."""
    settings = get_settings()

    if not settings.reasoning_model_name:
        yield "Smart Comms is not configured. Set REASONING_MODEL_NAME to enable chat."
        return

    async for chunk in stream_completion(
        settings=settings,
        messages=messages,
        profile="reasoning",
    ):
        yield chunk


def get_local_agent_provenance() -> dict[str, object]:
    """Return provenance metadata for the Smart Comms runtime profile."""
    settings = get_settings()
    config = resolve_profile_config(settings, "reasoning")
    return {
        "provider": config["provider"],
        "model_name": config["model_name"],
        "runtime_profile": "reasoning",
    }
