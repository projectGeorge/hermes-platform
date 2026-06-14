import os
from pathlib import Path

import chromadb
from chromadb.api import ClientAPI
from chromadb.api.types import EmbeddingFunction
from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2


_CHROMA_HOST = os.getenv("CHROMA_HOST", "http://localhost:8001")
_COLLECTION_SMARTS_COMMS = "smart_comms_memory"
_COLLECTION_CARRIER_SEARCH = "carrier_search_memory"

_client: ClientAPI | None = None
_embedding_fn: EmbeddingFunction | None = None


def _reset_client(host: str | None = None) -> None:
    global _client, _embedding_fn
    if host:
        global _CHROMA_HOST
        _CHROMA_HOST = host
    _client = None
    _embedding_fn = None


def _get_client() -> ClientAPI:
    global _client
    if _client is None:
        _client = chromadb.HttpClient(host=_CHROMA_HOST)
    return _client


def _get_embedding_fn() -> EmbeddingFunction:
    global _embedding_fn
    if _embedding_fn is None:
        _embedding_fn = ONNXMiniLM_L6_V2()
    return _embedding_fn


def get_collection(name: str):
    client = _get_client()
    ef = _get_embedding_fn()
    return client.get_or_create_collection(
        name=name,
        embedding_function=ef,
    )


def smart_comms_collection():
    return get_collection(_COLLECTION_SMARTS_COMMS)


def carrier_search_collection():
    return get_collection(_COLLECTION_CARRIER_SEARCH)


def upsert_document(
    collection_name: str,
    document_id: str,
    document: str,
    metadata: dict | None = None,
) -> None:
    col = get_collection(collection_name)
    col.upsert(
        ids=[document_id],
        documents=[document],
        metadatas=[metadata] if metadata else None,
    )


def similarity_query(
    collection_name: str,
    query: str,
    top_k: int = 5,
) -> list[dict]:
    col = get_collection(collection_name)
    results = col.query(
        query_texts=[query],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )
    snippets: list[dict] = []
    if not results.get("ids") or not results["ids"][0]:
        return snippets

    for i, doc_id in enumerate(results["ids"][0]):
        snippets.append({
            "id": doc_id,
            "document": results["documents"][0][i] if results.get("documents") else "",
            "metadata": results["metadatas"][0][i] if results.get("metadatas") else None,
            "distance": results["distances"][0][i] if results.get("distances") else None,
        })
    return snippets


def check_health() -> bool:
    try:
        client = _get_client()
        client.heartbeat()
        return True
    except Exception:
        return False


def check_health_cached() -> bool:
    return check_health()
