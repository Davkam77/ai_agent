from __future__ import annotations

import logging
from pathlib import Path

from app.config.settings import Settings
from app.ingestion.chunking import TextChunker
from app.llm.openai_client import OpenAIClient
from app.models import CleanDocument, VectorRecord
from app.storage.repositories import MetadataRepository
from app.storage.vector_store import LocalNumpyVectorStore
from app.utils import iter_json_files, read_json

logger = logging.getLogger(__name__)


class IngestionPipeline:
    def __init__(
        self,
        settings: Settings,
        repository: MetadataRepository,
        vector_store: LocalNumpyVectorStore,
        openai_client: OpenAIClient,
        chunk_max_chars: int = 1000,
        chunk_overlap_lines: int = 2,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.vector_store = vector_store
        self.openai_client = openai_client
        self.chunker = TextChunker(max_chars=chunk_max_chars, overlap_lines=chunk_overlap_lines)

    def run(self, bank_name: str | None = None, topic: str | None = None) -> list[Path]:
        written_files: list[Path] = []
        for clean_file in iter_json_files(self.settings.clean_output_dir):
            document = CleanDocument(**read_json(clean_file))
            if bank_name and document.bank_name.casefold() != bank_name.casefold():
                continue
            if topic and document.topic != topic:
                continue
            self._ingest_document(clean_file, document)
            written_files.append(clean_file)
        return written_files

    def _ingest_document(self, clean_file: Path, document: CleanDocument) -> None:
        active_hash = self.repository.get_active_document_hash(
            bank_name=document.bank_name,
            topic=document.topic,
            source_url=document.source_url,
        )
        previous_chunk_ids = self.repository.get_active_chunk_ids(
            bank_name=document.bank_name,
            topic=document.topic,
            source_url=document.source_url,
        )
        has_legacy_metadata = False
        missing_vector_ids: list[str] = []
        if active_hash == document.content_hash:
            has_legacy_metadata = self.repository.has_legacy_chunk_metadata(
                bank_name=document.bank_name,
                topic=document.topic,
                source_url=document.source_url,
            )
            missing_vector_ids = self.vector_store.missing_chunk_ids(previous_chunk_ids)
        if active_hash == document.content_hash and not has_legacy_metadata and not missing_vector_ids:
            logger.info("Skipping unchanged document %s", clean_file)
            return
        if active_hash == document.content_hash and has_legacy_metadata:
            logger.info(
                "Re-ingesting unchanged document due to legacy chunk metadata %s",
                clean_file,
            )
        if active_hash == document.content_hash and missing_vector_ids:
            logger.info(
                "Re-ingesting unchanged document due to missing vectors source=%s missing_vectors=%s",
                document.source_url,
                len(missing_vector_ids),
            )
        self.repository.deactivate_source(document.bank_name, document.topic, document.source_url)
        self.repository.insert_document(document, str(clean_file))

        chunks = self.chunker.chunk_document(document)
        if not chunks:
            logger.warning("No chunks produced for %s", clean_file)
            self.vector_store.remove(previous_chunk_ids)
            return

        embeddings = self.openai_client.embed_texts([chunk.content for chunk in chunks])
        self.repository.insert_chunks(chunks)
        self.vector_store.remove(previous_chunk_ids)
        self.vector_store.upsert(
            [
                VectorRecord(
                    chunk_id=chunk.chunk_id,
                    bank_name=chunk.bank_name,
                    topic=chunk.topic,
                    vector=embedding,
                    source_url=chunk.source_url,
                    page_title=chunk.page_title,
                    document_id=chunk.document_id,
                    section_name=chunk.section_name,
                    chunk_index=chunk.chunk_index,
                )
                for chunk, embedding in zip(chunks, embeddings)
            ]
        )
        section_count = len({chunk.section_name for chunk in chunks if chunk.section_name})
        logger.info(
            "Ingested source=%s page=%s clean_len=%s chunk_count=%s section_count=%s",
            document.source_url,
            document.page_title,
            len(document.clean_text),
            len(chunks),
            section_count,
        )
