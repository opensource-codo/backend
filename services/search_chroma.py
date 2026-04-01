# search_chroma.py
import os
from typing import Dict, Any, List, Tuple
from dotenv import load_dotenv
from openai import OpenAI
import chromadb

EMBED_MODEL = "text-embedding-3-small"
FUSION_ALPHA = 0.15
DEFAULT_THRESHOLD = 0.28  # 점수 컷오프

def to_similarity(dist: float) -> float:
    """
    Chroma(HNSW cosine)에서 distance ~= 1 - cosine_similarity.
    유사도로 변환: 1 - distance (0~1 범위로 가정).
    """
    sim = 1.0 - float(dist)
    # 경계값 보정
    if sim < 0: sim = 0.0
    if sim > 1: sim = 1.0
    return sim

def search_intent(user_text: str, top_k: int = 20) -> Dict[str, Any]:
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    openai = OpenAI(api_key=api_key)

    # 1) 쿼리 임베딩
    qvec = openai.embeddings.create(model=EMBED_MODEL, input=[user_text]).data[0].embedding

    # 2) 벡터 검색
    client = chromadb.PersistentClient(path="./chroma_db")
    col = client.get_collection("intents")

    res = col.query(
        query_embeddings=[qvec],
        n_results=top_k,
        include=["distances", "metadatas", "documents"]
    )
    dists = res.get("distances", [[]])[0]
    metas = res.get("metadatas", [[]])[0]

    # 3) view 가중치 및 late-fusion → function_key 단위로 집계
    by_fn: Dict[str, Dict[str, Any]] = {}
    count = min(len(metas), len(dists))
    for i in range(count):
        md = metas[i]
        fk = md["function_key"]
        view = md.get("view", "SHORT")
        w = float(md.get("weight", 1.0))
        sim = to_similarity(dists[i]) * w

        agg = by_fn.setdefault(fk, {"max": 0.0, "sum": 0.0, "views": [], "intent": md.get("intent")})
        agg["max"] = max(agg["max"], sim)
        agg["sum"] += sim
        agg["views"].append({"view": view, "score": sim})

    ranked: List[Tuple[str, float, Dict[str, Any]]] = []
    for fk, a in by_fn.items():
        final = a["max"] + FUSION_ALPHA * (a["sum"] - a["max"])
        ranked.append((fk, final, a))

    ranked.sort(key=lambda x: x[1], reverse=True)

    # 4) 응답 정형화
    candidates = []
    top = None
    for fk, score, a in ranked:
        item = {
            "intent": a.get("intent"),
            "function_key": fk,
            "score": round(score, 3),
            "views": sorted(a["views"], key=lambda x: x["score"], reverse=True)
        }
        if top is None:
            top = item
        candidates.append(item)

    status = "ok" if (top and top["score"] >= DEFAULT_THRESHOLD) else "low_confidence"
    return {
        "query": user_text,
        "status": status,
        "top": top,
        "candidates": candidates[:5]
    }