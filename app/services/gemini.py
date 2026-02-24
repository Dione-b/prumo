from typing import Any
from uuid import UUID

import google.generativeai as genai
from tenacity import (
    RetryCallState,
    retry,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings
from app.logger import get_logger
from app.schemas.business_rule import BusinessRuleSchema
from app.services.sanitizer import sanitize_llm_json

log = get_logger(__name__)

genai.configure(api_key=settings.gemini_api_key.get_secret_value())  # type: ignore[attr-defined]

SYSTEM_PROMPT_EXTRACTION = (
    "You are an expert technical business analyst. "
    "Your task is to extract structured information from raw, "
    "unstructured meeting notes or transcriptions.\n\n"
    "CRITICAL LANGUAGE RULE:\n"
    "The input text (`raw_text`) may be in any language "
    "(e.g., Portuguese, Spanish, English, German).\n"
    "1. You MUST map the extracted concepts to the strict "
    "English JSON keys provided in the schema.\n"
    "2. You MUST preserve the original language of the input "
    "text for all JSON values. DO NOT translate the business "
    "context, technical constraints, or acceptance criteria "
    "into English unless the original text was in English. "
    "Keep the exact domain terminology used by the user.\n\n"
    "Extract the following fields based on the schema:\n"
    "- client_name: The company or person requesting the project.\n"
    "- core_objective: The main problem the system solves.\n"
    "- technical_constraints: Mandatory technologies, deadlines, "
    "or infrastructure limits.\n"
    "- acceptance_criteria: What defines a successful delivery.\n"
    "- additional_notes: Any other relevant info.\n"
    "- confidence_level: Evaluate extraction quality as "
    '"HIGH", "MEDIUM", or "LOW" based on text clarity.'
)


def _log_retry(retry_state: RetryCallState) -> None:
    """Log a warning each time a retry is triggered."""
    wait = 0.0
    if retry_state.next_action is not None:
        wait = round(retry_state.next_action.sleep, 2)
    log.warning(
        "gemini_api_retry",
        attempt=retry_state.attempt_number,
        wait_seconds=wait,
    )


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=2, max=10),
    before_sleep=_log_retry,
    reraise=True,
)
async def _call_gemini(
    full_prompt: str,
) -> Any:
    """Execute the Gemini API call with automatic retries."""
    model = genai.GenerativeModel(  # type: ignore[attr-defined]
        model_name=settings.gemini_model,
        generation_config=genai.GenerationConfig(  # type: ignore[attr-defined]
            temperature=settings.gemini_temperature,
            response_mime_type="application/json",
            response_schema=BusinessRuleSchema,
        ),
    )
    return await model.generate_content_async(full_prompt)


async def extract_sanitized_business(
    raw_text: str,
    project_id: UUID,
) -> BusinessRuleSchema:
    """Call Gemini to extract structured business data.

    Includes automatic retries with exponential backoff
    and token usage logging.
    """
    full_prompt = f"{SYSTEM_PROMPT_EXTRACTION}\n\nRaw text for analysis:\n{raw_text}"

    response = await _call_gemini(full_prompt)
    parsed_data = sanitize_llm_json(response.text)
    result = BusinessRuleSchema(**parsed_data)

    # Log token usage for cost tracking / observability
    usage = getattr(response, "usage_metadata", None)
    if usage:
        log.info(
            "gemini_token_usage",
            prompt_tokens=usage.prompt_token_count,
            completion_tokens=usage.candidates_token_count,
            total_tokens=usage.total_token_count,
            project_id=str(project_id),
            extraction_confidence=result.confidence_level,
        )

    return result
