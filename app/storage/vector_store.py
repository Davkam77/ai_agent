from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from app.models import VectorRecord


class LocalNumpyVectorStore:
    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.root_dir / "index.json"
        self.vectors_path = self.root_dir / "vectors.npy"

    def upsert(self, records: list[VectorRecord]) -> None:
        if not records:
            return
        existing = self._load_state()
        for record in records:
            existing[record.chunk_id] = {
                "metadata": {
                    "chunk_id": record.chunk_id,
                    "bank_name": record.bank_name,
                    "topic": record.topic,
                },
                "vector": self._normalize(np.array(record.vector, dtype=np.float32)),
            }
        self._persist(existing)

    def remove(self, chunk_ids: list[str]) -> None:
        if not chunk_ids:
            return
        existing = self._load_state()
        for chunk_id in chunk_ids:
            existing.pop(chunk_id, None)
        self._persist(existing)

    def search(
        self,
        query_vector: list[float],
        top_k: int,
        topic: str,
        bank_name: str | None = None,
    ) -> list[tuple[str, float]]:
        state = self._load_state()
        if not state:
            return []
        filtered_ids: list[str] = []
        filtered_vectors: list[np.ndarray] = []
        for chunk_id, payload in state.items():
            metadata = payload["metadata"]
            if metadata["topic"] != topic:
                continue
            if bank_name and metadata["bank_name"].casefold() != bank_name.casefold():
                continue
            filtered_ids.append(chunk_id)
            filtered_vectors.append(payload["vector"])
        if not filtered_vectors:
            return []

        matrix = np.vstack(filtered_vectors)
        query = self._normalize(np.array(query_vector, dtype=np.float32))
        scores = matrix @ query
        ranked_indices = np.argsort(scores)[::-1][:top_k]
        return [(filtered_ids[index], float(scores[index])) for index in ranked_indices]

    def _load_state(self) -> dict[str, dict[str, object]]:
        if not self.index_path.exists() or not self.vectors_path.exists():
            return {}
        metadata = json.loads(self.index_path.read_text(encoding="utf-8"))
        vectors = np.load(self.vectors_path)
        state: dict[str, dict[str, object]] = {}
        for meta, vector in zip(metadata, vectors):
            state[meta["chunk_id"]] = {"metadata": meta, "vector": vector}
        return state

    def _persist(self, state: dict[str, dict[str, object]]) -> None:
        if not state:
            self.index_path.write_text("[]", encoding="utf-8")
            np.save(self.vectors_path, np.empty((0, 0), dtype=np.float32))
            return

        ordered_ids = sorted(state.keys())
        metadata = [state[chunk_id]["metadata"] for chunk_id in ordered_ids]
        vectors = np.vstack([state[chunk_id]["vector"] for chunk_id in ordered_ids])
        self.index_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        np.save(self.vectors_path, vectors)

    @staticmethod
    def _normalize(vector: np.ndarray) -> np.ndarray:
        norm = float(np.linalg.norm(vector))
        if norm == 0:
            return vector
        return vector / norm
