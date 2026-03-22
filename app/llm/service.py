from __future__ import annotations

import logging
import re

from app.llm.conversation import ConversationHandler
from app.llm.openai_client import OpenAIClient
from app.llm.prompts import (
    build_answer_system_prompt,
    build_answer_user_prompt,
    build_no_data_response,
    build_out_of_scope_response,
)
from app.models import AnswerPayload
from app.retrieval.classifier import TopicClassifier
from app.retrieval.query_utils import detect_language, normalize_text
from app.retrieval.service import RetrievalService

logger = logging.getLogger(__name__)


class SupportAgentService:
    def __init__(
        self,
        retrieval_service: RetrievalService,
        openai_client: OpenAIClient,
        classifier: TopicClassifier | None = None,
        conversation_handler: ConversationHandler | None = None,
    ) -> None:
        self.retrieval_service = retrieval_service
        self.openai_client = openai_client
        self.classifier = classifier or TopicClassifier()
        self.conversation_handler = conversation_handler or ConversationHandler()

    def answer_question(self, question: str) -> AnswerPayload:
        normalized_question = normalize_text(question)
        detected_language = detect_language(question)
        topic = self.classifier.classify(question)
        detected_bank = self.classifier.detect_bank(question)

        conversation_match = self.conversation_handler.match(
            question,
            detected_topic=topic,
            detected_bank=detected_bank,
        )
        if conversation_match:
            logger.info(
                "SupportAgent flow=%s question=%r normalized_question=%r detected_language=%s detected_topic=%s detected_bank=%s refusal_reason=%s source_count=%s",
                conversation_match.flow,
                question,
                normalized_question,
                conversation_match.detected_language,
                conversation_match.topic,
                detected_bank,
                None,
                0,
            )
            return AnswerPayload(
                question=question,
                topic=conversation_match.topic,
                answer_text=conversation_match.answer_text,
                sources=[],
                refusal=False,
                debug={
                    "flow": conversation_match.flow,
                    "intent": conversation_match.intent,
                    "normalized_question": normalized_question,
                    "detected_language": conversation_match.detected_language,
                    "detected_bank": detected_bank,
                    "detected_topic": topic,
                },
            )

        if not topic:
            logger.info(
                "SupportAgent flow=%s question=%r normalized_question=%r detected_language=%s detected_topic=%s detected_bank=%s refusal_reason=%s source_count=%s",
                "out_of_scope",
                question,
                normalized_question,
                detected_language,
                None,
                detected_bank,
                "unsupported_topic",
                0,
            )
            return AnswerPayload(
                question=question,
                topic=None,
                answer_text=build_out_of_scope_response(detected_language),
                sources=[],
                refusal=True,
                debug={
                    "flow": "out_of_scope",
                    "reason": "unsupported_topic",
                    "normalized_question": normalized_question,
                    "detected_language": detected_language,
                    "detected_bank": detected_bank,
                },
            )

        chunks, bank_filter, retrieval_debug = self.retrieval_service.retrieve(question, topic)
        if not chunks:
            logger.info(
                "SupportAgent flow=%s question=%r normalized_question=%r detected_language=%s detected_topic=%s detected_bank=%s refusal_reason=%s source_count=%s",
                "knowledge_retrieval",
                question,
                normalized_question,
                detected_language,
                topic,
                bank_filter,
                "no_relevant_chunks",
                0,
            )
            return AnswerPayload(
                question=question,
                topic=topic,
                answer_text=build_no_data_response(
                    detected_language,
                    topic=topic,
                    bank_name=bank_filter,
                ),
                sources=[],
                refusal=True,
                debug={
                    "flow": "knowledge_retrieval",
                    "reason": "no_relevant_chunks",
                    **retrieval_debug,
                },
            )

        grouped_sources: dict[tuple[str, str, str], set[str]] = {}
        for chunk in chunks:
            key = (chunk.bank_name, chunk.page_title, chunk.source_url)
            grouped_sources.setdefault(key, set())
            if chunk.section_name:
                grouped_sources[key].add(chunk.section_name)

        logger.info(
            "SupportAgent prompt_sources=%s",
            [
                {
                    "bank_name": bank_name,
                    "page_title": page_title,
                    "source_url": source_url,
                    "sections": sorted(section_names),
                }
                for (bank_name, page_title, source_url), section_names in grouped_sources.items()
            ],
        )

        answer = self.openai_client.generate_answer(
            system_prompt=build_answer_system_prompt(),
            user_prompt=build_answer_user_prompt(question, topic, chunks),
        ).strip()
        answer = self._sanitize_answer_text(answer)
        if not answer:
            answer = build_no_data_response(
                detected_language,
                topic=topic,
                bank_name=bank_filter,
            )

        sources: list[dict[str, str]] = []
        seen: set[tuple[str, str, str]] = set()
        for chunk in chunks:
            key = (chunk.bank_name, chunk.page_title, chunk.source_url)
            if key in seen:
                continue
            seen.add(key)
            sources.append(
                {
                    "bank_name": chunk.bank_name,
                    "page_title": chunk.page_title,
                    "source_url": chunk.source_url,
                }
            )

        logger.info(
            "SupportAgent flow=%s question=%r normalized_question=%r detected_language=%s detected_topic=%s detected_bank=%s refusal_reason=%s source_count=%s",
            "knowledge_retrieval",
            question,
            normalized_question,
            detected_language,
            topic,
            bank_filter,
            None,
            len(sources),
        )

        return AnswerPayload(
            question=question,
            topic=topic,
            answer_text=answer,
            sources=sources,
            refusal=False,
            debug={
                **retrieval_debug,
                "retrieved_chunks": [chunk.to_dict() for chunk in chunks],
            },
        )

    def _sanitize_answer_text(self, text: str) -> str:
        if not text:
            return ""
        cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
        cleaned = re.sub(r"\[?\s*chunk\s+\d+\s*\]?:?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"</?official_source>", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"</?bank>", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"</?page_title>", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"</?evidence>", "", cleaned, flags=re.IGNORECASE)

        filtered_lines: list[str] = []
        for raw_line in cleaned.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            lowered = line.casefold()
            if lowered.startswith(("bank:", "topic:", "title:", "page title:", "source url:", "content:", "user question:", "detected topic:")):
                continue
            filtered_lines.append(line)

        cleaned = "\n".join(filtered_lines).strip()
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned
