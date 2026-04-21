import logging
import os
from pathlib import Path
from typing import Optional

import chromadb
from sentence_transformers import SentenceTransformer

from codeassist.parser import CodeChunk

# Silence noisy startup output from HuggingFace / transformers libraries
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)

MODEL_NAME = "all-MiniLM-L6-v2"
COLLECTION_NAME = "codebase"
DEFAULT_DB = ".codeassist/db"

_model: Optional[SentenceTransformer] = None


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        # Suppress progress bars from huggingface_hub, transformers, safetensors.
        import huggingface_hub
        import tqdm as _tqdm
        huggingface_hub.utils.disable_progress_bars()
        orig_init = _tqdm.tqdm.__init__
        def _silent_init(self, *args, **kwargs):
            kwargs["disable"] = True
            orig_init(self, *args, **kwargs)
        _tqdm.tqdm.__init__ = _silent_init
        try:
            _model = SentenceTransformer(MODEL_NAME)
        finally:
            _tqdm.tqdm.__init__ = orig_init
            huggingface_hub.utils.enable_progress_bars()
    return _model


def _get_collection(db_path: str) -> chromadb.Collection:
    client = chromadb.PersistentClient(path=db_path)
    return client.get_or_create_collection(COLLECTION_NAME)


def db_exists(db_path: str = DEFAULT_DB) -> bool:
    return Path(db_path).exists()


def index_chunks(
    chunks: list[CodeChunk],
    db_path: str = DEFAULT_DB,
    batch_size: int = 64,
) -> int:
    """Embed chunks and upsert into ChromaDB. Returns number of chunks stored."""
    if not chunks:
        return 0

    model = get_model()
    collection = _get_collection(db_path)
    total = 0

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        texts = [c.content for c in batch]
        embeddings = model.encode(texts, show_progress_bar=False).tolist()

        ids = [f"{c.file_path}::{c.start_line}" for c in batch]
        metadatas = [
            {
                "file_path": c.file_path,
                "language": c.language,
                "start_line": c.start_line,
                "end_line": c.end_line,
                "name": c.name or "",
                "kind": c.kind or "chunk",
            }
            for c in batch
        ]

        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )
        total += len(batch)

    return total


def query_index(
    question: str,
    db_path: str = DEFAULT_DB,
    top_k: int = 5,
) -> list[dict]:
    """Return top_k most relevant chunks for the question."""
    model = get_model()
    collection = _get_collection(db_path)

    # Guard against querying an empty collection
    if collection.count() == 0:
        return []

    n = min(top_k, collection.count())
    embedding = model.encode([question], show_progress_bar=False).tolist()
    results = collection.query(
        query_embeddings=embedding,
        n_results=n,
        include=["documents", "metadatas", "distances"],
    )

    chunks: list[dict] = []
    if results["documents"]:
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            chunks.append({"content": doc, "metadata": meta, "distance": dist})
    return chunks
