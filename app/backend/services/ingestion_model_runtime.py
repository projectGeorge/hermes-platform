import json
from dataclasses import dataclass, field
from typing import Any
import re

import httpx

from app.backend.core.settings import Settings


class ModelExtractionError(RuntimeError):
    """Raised when the LM Studio model path fails."""


_FENCED_JSON_PATTERN = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)


def _extract_json_object(content: str) -> dict[str, Any]:
    stripped = content.strip()
    fenced_match = _FENCED_JSON_PATTERN.match(stripped)
    if fenced_match:
        stripped = fenced_match.group(1).strip()

    try:
        extracted = json.loads(stripped)
    except json.JSONDecodeError:
        raise ModelExtractionError(
            f"Invalid JSON from model: {content[:500]}"
        )

    if not isinstance(extracted, dict):
        raise ModelExtractionError(
            f"Model returned non-object JSON: {content[:500]}"
        )

    return extracted


@dataclass(frozen=True)
class ModelExtractionResult:
    extracted_payload: dict[str, Any]
    raw_model_response: str
    confidence_summary: dict[str, Any] | None
    normalization_warnings: list[str]
    provider: str
    model_name: str


async def extract_load_order_with_model(
    raw_text: str,
    settings: Settings,
) -> ModelExtractionResult:
    system_prompt = (
        "You are a freight forwarding data extraction assistant. "
        "Extract shipment details from the user's message and return ONLY a JSON object. "
        "Fields: customer_name (company name, never the contact person), origin_text (City, Country format), "
        "destination_text (City, Country format), "
        "origin_load_date (ISO 8601: YYYY-MM-DDTHH:MM:SS), "
        "destination_unload_date (ISO 8601: YYYY-MM-DDTHH:MM:SS), "
        "cargo_description, weight_kg (number only), customer_price (number only, in EUR), "
        "currency (3-letter code), adr_required (boolean, true only if dangerous goods mentioned), "
        "truck_type_id (integer: 1=tautliner, 2=reefer, 3=mega, only when explicitly mentioned). "
        "Rules:\n"
        "- customer_name must be the company, not the sender person.\n"
        "- If the footer or signature contains the company name, prefer that over the contact person's name.\n"
        "- Always infer the country when a city is mentioned (e.g. Valencia -> Valencia, ES).\n"
        "- CRITICAL: Extract BOTH origin_load_date AND destination_unload_date. These are equally important.\n"
        "- Date format examples:\n"
        "  * '15/06 a las 08:30 h' -> '2026-06-15T08:30:00'\n"
        "  * 'Miércoles 17/06 a las 14:00 h' -> '2026-06-17T14:00:00'\n"
        "  * 'Próximo lunes 15/06' -> '2026-06-15T00:00:00'\n"
        "  * '2026-06-15 08:30' -> '2026-06-15T08:30:00'\n"
        "- Use current year (2026) for dates unless another year is explicit.\n"
        "- Do not invent values that are not grounded in the message or strong freight-domain conventions.\n"
        "- If a field is ambiguous, omit it instead of guessing.\n"
        "- Keep dates and numeric fields normalized for machine parsing.\n"
        "- Omit fields you cannot find with any confidence.\n"
        "- Return ONLY the JSON object, no markdown, no explanation."
    )

    async with httpx.AsyncClient(timeout=settings.ingestion_model_timeout_seconds) as client:
        response = await client.post(
            f"{settings.lm_studio_base_url}/chat/completions",
            json={
                "model": settings.ingestion_model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": raw_text},
                ],
                "temperature": 0.1,
            },
        )

    if response.status_code != 200:
        raise ModelExtractionError(
            f"LM Studio returned status {response.status_code}: {response.text[:500]}"
        )

    body = response.json()
    content = body["choices"][0]["message"]["content"].strip()

    extracted = _extract_json_object(content)

    return ModelExtractionResult(
        extracted_payload=extracted,
        raw_model_response=content,
        confidence_summary=None,
        normalization_warnings=[],
        provider=settings.ingestion_model_provider,
        model_name=settings.ingestion_model_name,
    )
