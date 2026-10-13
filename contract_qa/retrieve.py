"""Cached OpenAI embeddings and exact NumPy cosine retrieval."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path

import numpy as np

from .budget import Budget, BudgetError, ConfigurationError, get_client

EMBEDDING_MODEL = "text-embedding-3-small"
BATCH_SIZE = 100


def cosine_scores(vectors, query) -> np.ndarray:
    """Zero vectors score zero; malformed/nonfinite vectors are rejected."""
    vectors = np.asarray(vectors, dtype=np.float64)
    query = np.asarray(query, dtype=np.float64)
    if vectors.ndim != 2 or query.ndim != 1 or vectors.shape[1] != len(query):
        raise ValueError("Expected an n-by-d matrix and a d-dimensional query")
    if not np.isfinite(vectors).all() or not np.isfinite(query).all():
        raise ValueError("Vectors must contain only finite numbers")
    denominator = np.linalg.norm(vectors, axis=1) * np.linalg.norm(query)
    return np.divide(vectors @ query, denominator, out=np.zeros(len(vectors)),
                     where=denominator != 0)


def rank_chunks(chunks: list[dict], vectors, query, k: int = 5,
                contract_id: str | None = None) -> list[dict]:
    """Return full chunks with score; ties preserve the input order."""
    if type(k) is not int or k < 0:
        raise ValueError("k must be a nonnegative integer")
    if len(chunks) != len(vectors):
        raise ValueError("Each vector needs one chunk")
    positions = [i for i, chunk in enumerate(chunks)
                 if contract_id is None or chunk["contract_id"] == contract_id]
    if not positions or k == 0:
        return []
    scores = cosine_scores(np.asarray(vectors)[positions], query)
    order = np.argsort(-scores, kind="stable")[:k]
    return [{**chunks[positions[i]], "score": float(scores[i])} for i in order]


def _atomic_array(path: Path, values):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temp = Path(handle.name)
        try:
            np.save(handle, values, allow_pickle=False)
            handle.flush()
            os.fsync(handle.fileno())
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
    os.replace(temp, path)


def _atomic_json(path: Path, value):
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as handle:
        temp = Path(handle.name)
        try:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
    os.replace(temp, path)


class Retriever:
    def __init__(self, data_dir: str | Path = "data", *, client=None,
                 budget: Budget | None = None):
        self.data_dir = Path(data_dir)
        self.cache_dir = self.data_dir / "embedding_cache"
        self.client = client
        self.budget = budget or Budget(self.data_dir)
        self.chunks: list[dict] | None = None
        self.vectors: np.ndarray | None = None

    def _cache_path(self, text: str) -> Path:
        digest = hashlib.sha256((EMBEDDING_MODEL + "\0" + text).encode()).hexdigest()
        return self.cache_dir / f"{digest}.npy"

    def _embed(self, texts: list[str]) -> np.ndarray:
        """Persist each successful batch, including queries; deduplicate by text."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        missing = []
        known = {}
        for text in dict.fromkeys(texts):
            if not isinstance(text, str) or not text.strip():
                raise ValueError("Embedding input must be nonempty text")
            path = self._cache_path(text)
            if path.exists():
                vector = np.load(path, allow_pickle=False)
                if vector.ndim != 1 or not len(vector) or not np.isfinite(vector).all():
                    raise ValueError(f"Invalid embedding cache entry: {path.name}")
                known[text] = vector
            else:
                missing.append(text)
        for start in range(0, len(missing), BATCH_SIZE):
            batch = missing[start:start + BATCH_SIZE]
            if self.client is None:
                self.client = get_client()
            client = self.client
            if hasattr(client, "with_options"):
                client = client.with_options(max_retries=0)
            # UTF-8 byte length upper-bounds tokens for plain embedding strings.
            input_upper = sum(len(text.encode("utf-8")) for text in batch)
            rates = self.budget.pricing.model(EMBEDDING_MODEL)
            if any(len(text.encode("utf-8")) > rates["max_input_tokens"] for text in batch):
                raise ValueError("Embedding input exceeds its conservative configured token limit")
            response = self.budget.run(
                EMBEDDING_MODEL, input_upper, 0,
                lambda: client.embeddings.create(model=EMBEDDING_MODEL, input=batch),
            )
            rows = sorted(response.data, key=lambda item: item.index)
            if [row.index for row in rows] != list(range(len(batch))):
                raise ValueError("Embedding response has missing or duplicate indexes")
            for text, row in zip(batch, rows):
                vector = np.asarray(row.embedding, dtype=np.float32)
                if vector.ndim != 1 or not len(vector) or not np.isfinite(vector).all():
                    raise ValueError("Embedding API returned an invalid vector")
                _atomic_array(self._cache_path(text), vector)
                known[text] = vector
        if not texts:
            return np.empty((0, 0), dtype=np.float32)
        return np.stack([known[text] for text in texts])

    def _read_chunks(self) -> list[dict]:
        path = self.data_dir / "chunks.jsonl"
        if not path.exists():
            raise ConfigurationError("data/chunks.jsonl is missing. Run python -m contract_qa.ingest first.")
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    def build_index(self, chunks: list[dict] | None = None) -> np.ndarray:
        if chunks is None:
            chunks = self._read_chunks()
        if not chunks:
            raise ValueError("No chunks to embed")
        ids = [chunk["chunk_id"] for chunk in chunks]
        if len(set(ids)) != len(ids):
            raise ValueError("Chunk IDs must be unique")
        self.vectors = self._embed([chunk["text"] for chunk in chunks])
        self.chunks = chunks
        _atomic_array(self.data_dir / "embeddings.npy", self.vectors)
        _atomic_json(self.data_dir / "ids.json", ids)
        return self.vectors

    def search(self, question: str, k: int = 5,
               contract_id: str | None = None) -> list[dict]:
        if not isinstance(question, str) or not question.strip():
            raise ValueError("Question must be nonempty text")
        if type(k) is not int or k < 0:
            raise ValueError("k must be a nonnegative integer")
        if k == 0:
            return []
        if self.chunks is None:
            chunks = self._read_chunks()
            if contract_id is not None and not any(c["contract_id"] == contract_id for c in chunks):
                return []
            self.build_index(chunks)
        if contract_id is not None and not any(c["contract_id"] == contract_id for c in self.chunks):
            return []
        query = self._embed([question])[0]
        return rank_chunks(self.chunks, self.vectors, query, k, contract_id)


def search(question: str, k: int = 5, contract_id: str | None = None, *,
           retriever: Retriever | None = None) -> list[dict]:
    return (retriever or Retriever()).search(question, k, contract_id)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", nargs="?")
    parser.add_argument("--contract", dest="contract_id")
    parser.add_argument("--data-dir", default="data")
    args = parser.parse_args()
    try:
        retriever = Retriever(args.data_dir)
        if args.question:
            print(json.dumps(retriever.search(args.question, contract_id=args.contract_id), indent=2))
        else:
            vectors = retriever.build_index()
            print(f"Cached embeddings for {len(vectors)} chunks.")
    except (ConfigurationError, BudgetError, ValueError, OSError) as exc:
        parser.exit(2, f"{exc}\n")
    except Exception:
        parser.exit(2, "API request failed; any pending budget reservation is retained.\n")


if __name__ == "__main__":
    main()
