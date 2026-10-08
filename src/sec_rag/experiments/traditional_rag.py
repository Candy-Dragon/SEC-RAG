"""Traditional RAG baseline using BM25 evidence followed by one model call."""

from __future__ import annotations

from typing import Any

from sec_rag.experiments.run_record import BaselineOutputValidationError, create_run_record
from sec_rag.experiments.prompts import (
    TRADITIONAL_RAG_RULES,
    prompt_metadata,
    system_prompt,
)
from sec_rag.experiments.structured_output import parse_common_output
from sec_rag.knowledge.bm25_search import GuidelineBM25Retriever
from sec_rag.llm.deepseek_client import DeepSeekAPIError, DeepSeekClient
from sec_rag.llm.types import ChatMessage


def format_evidence(results: list[dict[str, object]]) -> str:
    blocks: list[str] = []
    for result in results:
        blocks.append(
            "\n".join(
                [
                    f"[证据{result['rank']}]",
                    f"指南：{result['source_file']}",
                    f"页码：{result['page_start']}-{result['page_end']}",
                    f"章节：{result['section_heading'] or '未识别'}",
                    f"原文：{result['text']}",
                ]
            )
        )
    return "\n\n".join(blocks)


def run_traditional_rag(
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
        ChatMessage(role="system", content=system_prompt(TRADITIONAL_RAG_RULES)),
        ChatMessage(role="user", content=user_prompt),
    ]
    response = DeepSeekClient().chat(messages, json_output=True)
    try:
        parsed, validation = parse_common_output(
            response.content,
            evidence_count=len(retrieval),
            expected_sufficiency="null",
        )
    except DeepSeekAPIError as error:
        failed = create_run_record(
            method="traditional_rag", question=question, messages=messages,
            response=response, retrieval=retrieval,
            method_output={"validation_error": str(error), "raw_model_response": response.raw_response},
            prompt_info=prompt_metadata("traditional_rag"),
        )
        raise BaselineOutputValidationError(str(error), failed) from error
    return create_run_record(
        method="traditional_rag",
        question=question,
        messages=messages,
        response=response,
        retrieval=retrieval,
        answer_override=parsed["answer"],
        method_output={**parsed, "output_validation": validation},
        prompt_info=prompt_metadata("traditional_rag"),
    )
