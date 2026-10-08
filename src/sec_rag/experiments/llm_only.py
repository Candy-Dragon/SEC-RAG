"""LLM-only baseline: answer from the model without guideline retrieval."""

from __future__ import annotations

from typing import Any

from sec_rag.experiments.run_record import BaselineOutputValidationError, create_run_record
from sec_rag.experiments.prompts import LLM_ONLY_RULES, prompt_metadata, system_prompt
from sec_rag.experiments.structured_output import parse_common_output
from sec_rag.llm.deepseek_client import DeepSeekClient
from sec_rag.llm.deepseek_client import DeepSeekAPIError
from sec_rag.llm.types import ChatMessage


def run_llm_only(question: str) -> dict[str, Any]:
    question = question.strip()
    if not question:
        raise ValueError("Question cannot be empty.")
    messages = [
        ChatMessage(role="system", content=system_prompt(LLM_ONLY_RULES)),
        ChatMessage(role="user", content=question),
    ]
    response = DeepSeekClient().chat(messages, json_output=True)
    try:
        parsed, validation = parse_common_output(
            response.content, evidence_count=0, expected_sufficiency="null"
        )
    except DeepSeekAPIError as error:
        failed = create_run_record(
            method="llm_only", question=question, messages=messages,
            response=response, method_output={"validation_error": str(error), "raw_model_response": response.raw_response},
            prompt_info=prompt_metadata("llm_only"),
        )
        raise BaselineOutputValidationError(str(error), failed) from error
    return create_run_record(
        method="llm_only",
        question=question,
        messages=messages,
        response=response,
        answer_override=parsed["answer"],
        method_output={**parsed, "output_validation": validation},
        prompt_info=prompt_metadata("llm_only"),
    )
