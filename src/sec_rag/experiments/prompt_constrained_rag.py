"""Prompt-constrained RAG baseline with evidence-only generation rules."""

from __future__ import annotations

from typing import Any

from sec_rag.experiments.prompts import (
    PROMPT_CONSTRAINED_RULES,
    prompt_metadata,
    system_prompt,
)
from sec_rag.experiments.run_record import BaselineOutputValidationError, create_run_record
from sec_rag.experiments.structured_output import parse_common_output
from sec_rag.experiments.traditional_rag import format_evidence
from sec_rag.knowledge.bm25_search import GuidelineBM25Retriever
from sec_rag.llm.deepseek_client import DeepSeekAPIError, DeepSeekClient
from sec_rag.llm.types import ChatMessage


def run_prompt_constrained_rag(
    question: str, *, top_k: int = 5, disease: str | None = None,
    retrieval: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    question = question.strip()
    if not question:
        raise ValueError("Question cannot be empty.")
    retrieval = retrieval if retrieval is not None else GuidelineBM25Retriever().search(question, top_k=top_k, disease=disease)
    if not retrieval:
        raise ValueError("No guideline evidence was retrieved.")
    user_prompt = f"问题：\n{question}\n\n检索证据：\n{format_evidence(retrieval)}"
    messages = [
        ChatMessage(role="system", content=system_prompt(PROMPT_CONSTRAINED_RULES)),
        ChatMessage(role="user", content=user_prompt),
    ]
    response = DeepSeekClient().chat(messages, json_output=True)
    try:
        parsed, validation = parse_common_output(
            response.content,
            evidence_count=len(retrieval),
            expected_sufficiency="boolean",
        )
    except DeepSeekAPIError as error:
        failed = create_run_record(
            method="prompt_constrained_rag", question=question, messages=messages,
            response=response, retrieval=retrieval,
            method_output={"validation_error": str(error), "raw_model_response": response.raw_response},
            prompt_info=prompt_metadata("prompt_constrained_rag"),
        )
        raise BaselineOutputValidationError(str(error), failed) from error
    method_output = {**parsed, "output_validation": validation}
    return create_run_record(
        method="prompt_constrained_rag",
        question=question,
        messages=messages,
        response=response,
        retrieval=retrieval,
        answer_override=str(parsed["answer"]),
        method_output=method_output,
        prompt_info=prompt_metadata("prompt_constrained_rag"),
    )
