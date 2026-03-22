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
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.vector_store = vector_store
        self.openai_client = openai_client
        self.chunker = TextChunker()

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
        if active_hash == document.content_hash:
            logger.info("Skipping unchanged document %s", clean_file)
            return

        previous_chunk_ids = self.repository.get_active_chunk_ids(
            bank_name=document.bank_name,
            topic=document.topic,
            source_url=document.source_url,
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
                )
                for chunk, embedding in zip(chunks, embeddings)
            ]
        )
        logger.info("Ingested %s chunks from %s", len(chunks), clean_file)
