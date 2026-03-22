from __future__ import annotations

import logging
from collections import defaultdict

from app.llm.openai_client import OpenAIClient
from app.models import RetrievedChunk
from app.retrieval.classifier import BANK_ALIASES, TopicClassifier
from app.retrieval.query_utils import (
    build_retrieval_query,
    detect_language,
    normalize_text,
    significant_tokens,
    tokenize_text,
)
from app.storage.repositories import MetadataRepository
from app.storage.vector_store import LocalNumpyVectorStore

logger = logging.getLogger(__name__)


RankedItem = tuple[RetrievedChunk, float, float, float]
SourceKey = tuple[str, str, str]


class RetrievalService:
    def __init__(
        self,
        repository: MetadataRepository,
        vector_store: LocalNumpyVectorStore,
        openai_client: OpenAIClient,
        classifier: TopicClassifier | None = None,
        min_score: float = 0.22,
        top_k: int = 5,
        candidate_pool_size: int = 24,
        min_combined_score: float = 0.28,
        min_lexical_score: float = 0.12,
        max_chunks_per_source: int = 3,
        adjacent_window: int = 1,
        debug_verbose: bool = False,
    ) -> None:
        self.repository = repository
        self.vector_store = vector_store
        self.openai_client = openai_client
        self.classifier = classifier or TopicClassifier()
        self.min_score = min_score
        self.top_k = top_k
        self.candidate_pool_size = max(candidate_pool_size, top_k)
        self.min_combined_score = min_combined_score
        self.min_lexical_score = min_lexical_score
        self.max_chunks_per_source = max(1, max_chunks_per_source)
        self.adjacent_window = max(0, adjacent_window)
        self.debug_verbose = debug_verbose

    def retrieve(self, question: str, topic: str) -> tuple[list[RetrievedChunk], str | None, dict[str, object]]:
        detected_banks = self.classifier.detect_banks(question)
        bank_filter = detected_banks[0] if len(detected_banks) == 1 else None
        normalized_question = normalize_text(question)
        detected_language = detect_language(question)
        retrieval_query = build_retrieval_query(
            question,
            topic,
            bank_name=bank_filter,
            bank_aliases=BANK_ALIASES.get(bank_filter, ()),
        )
        query_vector = self.openai_client.embed_texts([retrieval_query])[0]
        semantic_matches = self.vector_store.search(
            query_vector=query_vector,
            top_k=self.candidate_pool_size,
            topic=topic,
            bank_name=bank_filter,
        )
        semantic_scores = {chunk_id: score for chunk_id, score in semantic_matches}
        candidates = self.repository.list_active_chunks(topic=topic, bank_name=bank_filter)
        ranked = self._rank_candidates(
            question=question,
            retrieval_query=retrieval_query,
            candidates=candidates,
            semantic_scores=semantic_scores,
        )

        selected_ranked = [item for item in ranked if item[1] >= self.min_combined_score]
        if not selected_ranked:
            selected_ranked = [
                item
                for item in ranked
                if item[2] >= self.min_score and item[3] >= self.min_lexical_score
            ]
        selected_ranked = self._select_source_aware(
            selected_ranked,
            bank_filter=bank_filter,
            requested_banks=detected_banks,
        )
        selected = [chunk for chunk, _combined, _semantic, _lexical in selected_ranked[: self.top_k]]

        debug = {
            "flow": "knowledge_retrieval",
            "normalized_question": normalized_question,
            "detected_language": detected_language,
            "bank_filter": bank_filter,
            "detected_banks": detected_banks,
            "retrieval_query": retrieval_query,
            "candidate_count": len(candidates),
            "ranked_count": len(ranked),
            "top_retrieved_chunks": [
                {
                    "chunk_id": chunk.chunk_id,
                    "bank_name": chunk.bank_name,
                    "page_title": chunk.page_title,
                    "source_url": chunk.source_url,
                    "section_name": chunk.section_name,
                    "chunk_index": chunk.chunk_index,
                    "semantic_score": round(semantic, 4),
                    "lexical_score": round(lexical, 4),
                    "combined_score": round(combined, 4),
                }
                for chunk, combined, semantic, lexical in ranked[: max(self.top_k, 8)]
            ],
            "top_retrieved_sources": self._build_source_debug(selected),
        }
        if not selected:
            debug["reason"] = "no_relevant_chunks"

        logger.info(
            "Retrieval question=%r normalized_question=%r language=%s topic=%s bank=%s candidate_count=%s ranked_count=%s source_count=%s",
            question,
            normalized_question,
            detected_language,
            topic,
            bank_filter,
            len(candidates),
            len(ranked),
            len({chunk.source_url for chunk in selected}),
        )
        logger.info("Retrieval selected_sources=%s", debug["top_retrieved_sources"])
        if self.debug_verbose:
            logger.info("Retrieval ranked_chunks=%s", debug["top_retrieved_chunks"])
        if not selected:
            logger.info("Retrieval refusal_reason=no_relevant_chunks")

        return selected, bank_filter, debug

    def _rank_candidates(
        self,
        question: str,
        retrieval_query: str,
        candidates: list[RetrievedChunk],
        semantic_scores: dict[str, float],
    ) -> list[RankedItem]:
        exact_tokens = significant_tokens(question)
        query_tokens = significant_tokens(retrieval_query)
        question_phrases = self._question_phrases(question)
        ranked: list[RankedItem] = []

        for chunk in candidates:
            semantic = semantic_scores.get(chunk.chunk_id, 0.0)
            lexical = self._lexical_score(
                chunk,
                exact_tokens=exact_tokens,
                query_tokens=query_tokens,
                question_phrases=question_phrases,
            )
            combined = semantic + lexical
            if semantic <= 0 and lexical < self.min_lexical_score:
                continue
            chunk.score = combined
            ranked.append((chunk, combined, semantic, lexical))

        ranked.sort(key=lambda item: (item[1], item[3], item[2]), reverse=True)
        return ranked

    def _lexical_score(
        self,
        chunk: RetrievedChunk,
        exact_tokens: list[str],
        query_tokens: list[str],
        question_phrases: list[str],
    ) -> float:
        searchable_text = normalize_text(
            f"{chunk.bank_name}\n{chunk.page_title}\n{chunk.section_name}\n{chunk.content}"
        )
        searchable_tokens = set(tokenize_text(searchable_text))
        if not searchable_tokens:
            return 0.0

        query_token_set = set(query_tokens)
        exact_token_set = set(exact_tokens)
        overlap = query_token_set & searchable_tokens
        if not overlap:
            return 0.0

        exact_overlap = exact_token_set & searchable_tokens
        title_tokens = set(tokenize_text(chunk.page_title))
        section_tokens = set(tokenize_text(chunk.section_name))
        title_overlap = exact_token_set & title_tokens
        section_overlap = exact_token_set & section_tokens
        topic_coverage = len(overlap) / max(len(query_token_set), 1)
        exact_coverage = len(exact_overlap) / max(len(exact_token_set), 1) if exact_token_set else 0.0
        long_exact_overlap = sum(1 for token in exact_overlap if len(token) >= 5)
        all_exact_matched = bool(exact_token_set) and exact_token_set <= searchable_tokens
        phrase_match = any(phrase in searchable_text for phrase in question_phrases)
        product_phrase_match = any(
            marker in searchable_text
            for phrase in question_phrases
            for marker in (
                f"product {phrase}",
                f"product: {phrase}",
                f"section {phrase}",
                f"section: {phrase}",
                f"branch {phrase}",
                f"branch: {phrase}",
            )
        )

        score = 0.0
        score += topic_coverage * 0.45
        score += exact_coverage * 0.25
        score += min(len(title_overlap), 2) * 0.06
        score += min(len(section_overlap), 2) * 0.05
        score += min(long_exact_overlap, 3) * 0.05
        if all_exact_matched:
            score += 0.08
        if phrase_match:
            score += 0.18
        if product_phrase_match:
            score += 0.12
        return min(score, 0.8)

    def _question_phrases(self, question: str) -> list[str]:
        words = [word for word in normalize_text(question).split() if len(word) > 2]
        phrases: list[str] = []
        seen: set[str] = set()
        for size in (3, 2):
            for index in range(len(words) - size + 1):
                phrase = " ".join(words[index : index + size]).strip()
                if len(phrase) < 6 or phrase in seen:
                    continue
                seen.add(phrase)
                phrases.append(phrase)
        return phrases

    def _select_source_aware(
        self,
        ranked: list[RankedItem],
        bank_filter: str | None,
        requested_banks: list[str] | None = None,
    ) -> list[RankedItem]:
        if not ranked:
            return []

        source_groups: dict[SourceKey, list[RankedItem]] = defaultdict(list)
        for item in ranked:
            key = (item[0].bank_name, item[0].page_title, item[0].source_url)
            source_groups[key].append(item)

        for group in source_groups.values():
            group.sort(key=lambda item: (item[1], item[3], item[2]), reverse=True)

        source_order = sorted(
            source_groups.keys(),
            key=lambda key: self._source_score(source_groups[key]),
            reverse=True,
        )
        if not bank_filter:
            source_order = self._interleave_sources_by_bank(source_order)

        selected: list[RankedItem] = []
        selected_ids: set[str] = set()
        if not bank_filter and requested_banks:
            for bank_name in requested_banks:
                bank_sources = [key for key in source_order if key[0] == bank_name]
                if not bank_sources:
                    continue
                for item in self._pick_chunks_with_context(source_groups[bank_sources[0]]):
                    chunk_id = item[0].chunk_id
                    if chunk_id in selected_ids:
                        continue
                    selected.append(item)
                    selected_ids.add(chunk_id)
                    if len(selected) >= self.top_k:
                        return selected

        for key in source_order:
            group_items = source_groups[key]
            for item in self._pick_chunks_with_context(group_items):
                chunk_id = item[0].chunk_id
                if chunk_id in selected_ids:
                    continue
                selected.append(item)
                selected_ids.add(chunk_id)
                if len(selected) >= self.top_k:
                    return selected

        for item in ranked:
            chunk_id = item[0].chunk_id
            if chunk_id in selected_ids:
                continue
            selected.append(item)
            selected_ids.add(chunk_id)
            if len(selected) >= self.top_k:
                break
        return selected

    def _pick_chunks_with_context(self, ranked_items: list[RankedItem]) -> list[RankedItem]:
        if not ranked_items:
            return []
        max_items = min(self.max_chunks_per_source, self.top_k)
        selected: list[RankedItem] = [ranked_items[0]]
        if max_items == 1:
            return selected

        top_chunk = ranked_items[0][0]
        top_section = (top_chunk.section_name or "").casefold()
        top_index = top_chunk.chunk_index

        def maybe_append(item: RankedItem) -> None:
            if item in selected:
                return
            selected.append(item)

        for item in ranked_items[1:]:
            if len(selected) >= max_items:
                break
            chunk = item[0]
            same_section = top_section and chunk.section_name.casefold() == top_section
            is_adjacent = abs(chunk.chunk_index - top_index) <= self.adjacent_window if top_index or chunk.chunk_index else False
            if same_section and (is_adjacent or self.adjacent_window == 0):
                maybe_append(item)

        for item in ranked_items[1:]:
            if len(selected) >= max_items:
                break
            chunk = item[0]
            is_adjacent = abs(chunk.chunk_index - top_index) <= self.adjacent_window if top_index or chunk.chunk_index else False
            if is_adjacent:
                maybe_append(item)

        for item in ranked_items[1:]:
            if len(selected) >= max_items:
                break
            maybe_append(item)
        return selected

    @staticmethod
    def _source_score(items: list[RankedItem]) -> float:
        top = items[0][1]
        secondary = sum(item[1] for item in items[:2]) / max(min(len(items), 2), 1)
        return top + secondary * 0.15

    def _interleave_sources_by_bank(self, source_order: list[SourceKey]) -> list[SourceKey]:
        grouped: dict[str, list[SourceKey]] = defaultdict(list)
        for key in source_order:
            grouped[key[0]].append(key)
        interleaved: list[SourceKey] = []
        while grouped:
            for bank_name in list(grouped.keys()):
                if not grouped[bank_name]:
                    grouped.pop(bank_name, None)
                    continue
                interleaved.append(grouped[bank_name].pop(0))
                if not grouped[bank_name]:
                    grouped.pop(bank_name, None)
        return interleaved

    @staticmethod
    def _build_source_debug(chunks: list[RetrievedChunk]) -> list[dict[str, object]]:
        sources: list[dict[str, object]] = []
        section_map: dict[tuple[str, str, str], set[str]] = defaultdict(set)
        seen: set[tuple[str, str, str]] = set()
        for chunk in chunks:
            key = (chunk.bank_name, chunk.page_title, chunk.source_url)
            if chunk.section_name:
                section_map[key].add(chunk.section_name)
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
                    "sections": sorted(section_map.get(key, set())),
                }
            )
        return sources
