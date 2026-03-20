import chromadb
from chromadb.config import Settings
import sqlite3
from typing import List, Dict, Any, Optional
import os
import numpy as np
from openai import OpenAI
from dotenv import load_dotenv
import re
from collections import defaultdict

load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")

# OpenAI 클라이언트 초기화
openai_client = OpenAI(api_key=api_key)

# 튜닝 가중치
VIEW_WEIGHT = {"SHORT":1.0, "DESC": 0.7, "HELP": 0.4}
# late fusion: 최종 스코어 = max + bonus*(sum - max)
FUSION_BONUS = 0.15
# 최종 신뢰 임계치 (튜닝 지점)
DEFAULT_THRESHOLD = 0.28

#============================

def _first_sentence(text: str, max_len: int = 120) -> str:
    """도움말/설명에서 첫 문장 한 줄 요약."""
    if not text:
        return ""
    s = re.split(r"[.!?。\n]", text.strip())[0]
    s = s.strip()
    return s[:max_len]


def guess_aliases(intent: str, function_key: str) -> List[str]:
    """
    간단 규칙 기반 동의어/별칭 생성.
    - 필요 시 사전(룰)만 보강해도 효과적.
    """
    intent = (intent or "").strip()
    fkey = (function_key or "").strip()

    aliases: set[str] = set()
    if fkey:
        aliases.add(fkey)
        parts = re.split(r"[_\-]+", fkey)
        if len(parts) > 1:
            aliases.add(" ".join(parts))  # e.g., rename_file -> "rename file"

    # 파일 삭제/복사/붙여넣기/잘라내기
    if any(k in intent for k in ["삭제", "지우", "제거"]) or "delete" in fkey:
        aliases.update(["파일 삭제", "파일 제거", "파일 지우기", "delete file", "del", "Shift+Delete", "휴지통", "영구 삭제"])

    if any(k in intent for k in ["붙여넣", "붙여", "paste"]) or "paste" in fkey:
        aliases.update(["파일 붙여넣기", "paste file", "Ctrl+V"])

    if any(k in intent for k in ["복사", "copy"]) or "copy" in fkey:
        aliases.update(["파일 복사", "copy file", "Ctrl+C"])

    if any(k in intent for k in ["잘라내", "자르기", "cut"]) or "cut" in fkey:
        aliases.update(["파일 잘라내기", "cut file", "Ctrl+X"])

    if any(k in intent for k in ["변경", "이름", "rename"]) or "rename" in fkey:
        aliases.update(["파일 이름 변경", "rename file", "F12"])

    # 제어판
    if any(k in intent for k in ["제어판", "control panel", "컨트롤 패널"]) or "control_panel" in fkey:
        aliases.update(["제어판", "Control Panel", "control panel", "컨트롤 패널"])

    # 캡처/스크린샷
    if any(k in intent for k in ["캡처", "스크린샷", "스크린 캡처", "프린트스크린", "화면", "screenshot", "screen"]) or "screenshot" in fkey:
        aliases.update(["스크린샷", "캡처", "PrintScreen", "screenshot", "PrtSc", "Win+Shift+S", "스니핑툴", "Snipping Tool"])

    # 전원/재시작/종료 (예시)
    if any(k in intent for k in ["재시작", "리부트", "restart"]) or "restart" in fkey:
        aliases.update(["재시작", "다시 시작", "restart", "win restart"])
    if any(k in intent for k in ["종료", "끄기", "shutdown"]) or "shutdown" in fkey:
        aliases.update(["종료", "shutdown", "전원 끄기"])


    if "프린터" in intent and any(k in intent for k in ["초기화", "재설정", "리셋"]):
        aliases.update(["프린터 초기화", "프린터 재설정", "프린터 리셋", "인쇄 초기화", "print reset"])

    return sorted(aliases)


def short_hint_from_help(help_text: str, intent: str) -> str:
    """SHORT 뷰에 넣을 핵심 한 줄. 도움말 기반으로 뽑고, 없으면 intent 사용."""
    s = _first_sentence(help_text, max_len=100)
    return s if s else intent


def make_one_liner_description(intent: str, help_text: str) -> str:
    """DESC 뷰에 들어갈 1~2문장 설명."""
    base = _first_sentence(help_text, max_len=140)
    if base:
        return base
    return f"{intent} 기능입니다."


def _to_similarity(distance: float, metric: str = "cosine") -> float:
    """
    Chroma distance -> similarity 변환.
    - cosine: sim = 1 - distance
    - 기타    : sim = 1 / (1 + distance)
    """
    if distance is None:
        return 0.0
    if metric == "cosine":
        return max(0.0, 1.0 - float(distance))
    return 1.0 / (1.0 + float(distance))

#=========================
class ChromaDBEmbedding:
    def __init__(self, db_path: str = "assistant.db", chroma_persist_directory: str = "./chroma_db"):
        """
        ChromaDB 임베딩 클래스 초기화

        Args:
            db_path: SQLite 데이터베이스 경로
            chroma_persist_directory: ChromaDB 저장 디렉토리
        """
        self.db_path = db_path
        self.chroma_persist_directory = chroma_persist_directory

        # 컬렉션 속성들을 None으로 초기화
        self.intents_collection = None
        self.functions_collection = None
        self.help_contents_collection = None
        self.unified_collection = None

        # ChromaDB 클라이언트 초기화
        try:
            self.client = chromadb.PersistentClient(
                path=chroma_persist_directory,
                settings=Settings(
                    anonymized_telemetry=False
                )
            )

            # 컬렉션 초기화
            self._init_collections()
        except Exception as e:
            print(f"ChromaDB 초기화 중 오류 발생: {e}")
            # 오류 발생 시에도 기본 컬렉션 객체 생성
            self._create_dummy_collections()

    def _create_dummy_collections(self):
        """오류 발생 시 더미 컬렉션을 생성합니다."""
        try:
            # 더미 컬렉션 생성 (실제로는 사용되지 않음)
            self.intents_collection = self.client.get_or_create_collection(
                name="intents_dummy",
                metadata={"description": "더미 컬렉션"}
            )
            self.functions_collection = self.client.get_or_create_collection(
                name="functions_dummy",
                metadata={"description": "더미 컬렉션"}
            )
            self.help_contents_collection = self.client.get_or_create_collection(
                name="help_contents_dummy",
                metadata={"description": "더미 컬렉션"}
            )
            self.unified_collection = self.client.get_or_create_collection(
                name="unified_search_dummy",
                metadata={"description": "더미 컬렉션"}
            )
        except Exception as e:
            print(f"더미 컬렉션 생성 실패: {e}")

    def _openai_embedding_function(self, texts):
        """OpenAI 임베딩 함수 (배치 처리)"""
        embeddings = []
        try:
            # 배치로 한 번에 처리
            response = openai_client.embeddings.create(
                model="text-embedding-3-small",
                input=texts
            )
            embeddings = [data.embedding for data in response.data]
        except Exception as e:
            print(f"배치 임베딩 오류: {e}")
            # 개별 처리로 폴백
            for text in texts:
                try:
                    response = openai_client.embeddings.create(
                        model="text-embedding-3-small",
                        input=[text]
                    )
                    embeddings.append(response.data[0].embedding)
                except Exception as e:
                    print(f"개별 임베딩 오류: {e}")
                    # 오류 시 0으로 채워진 벡터 반환
                    embeddings.append([0.0] * 1536)  # text-embedding-3-small의 차원
        return embeddings

    def _init_collections(self):
        """ChromaDB 컬렉션들을 초기화합니다."""
        try:
            # intents 컬렉션
            self.intents_collection = self.client.get_or_create_collection(
                name="intents",
                metadata={"description": "사용자 의도(intent) 데이터"}
            )

            # functions 컬렉션
            self.functions_collection = self.client.get_or_create_collection(
                name="functions",
                metadata={"description": "함수 정보 데이터"}
            )

            # help_contents 컬렉션
            self.help_contents_collection = self.client.get_or_create_collection(
                name="help_contents",
                metadata={"description": "도움말 내용 데이터"}
            )

            # 통합 검색용 컬렉션
            self.unified_collection = self.client.get_or_create_collection(
                name="unified_intents",
                metadata={"description": "intent 통합 문서", "hnsw:space": "cosine"}
            )

            print("ChromaDB 컬렉션이 성공적으로 초기화되었습니다.")

        except Exception as e:
            print(f"컬렉션 초기화 중 오류 발생: {e}")
            raise e

    def get_db_connection(self):
        """SQLite 데이터베이스 연결을 반환합니다."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def embed_text(self, text: str) -> List[float]:
        """OpenAI Embedding API로 텍스트를 임베딩합니다."""
        try:
            response = openai_client.embeddings.create(
                model="text-embedding-3-small",
                input=[text]
            )
            return response.data[0].embedding
        except Exception as e:
            print(f"임베딩 오류: {e}")
            return []

    def load_and_embed_unified_intents(self):
        """
        v_intent_docs를 읽어 intent당 3개 뷰(SHORT/DESC/HELP) 문서를 생성해 임베딩한다.
        - SHORT: 의도/함수키/별칭/핵심 한줄
        - DESC : 1~2문장 요약 설명
        - HELP : 잘린 원 도움말(노이즈 줄이기 위해 400~800자 권장)
        """
        if not self.unified_collection:
            print("unified_collection이 초기화되지 않았습니다.")
            return

        conn = self.get_db_connection()
        cur = conn.execute("""
            SELECT intent_id, intent, function_key, function_name, help_text
            FROM v_intent_docs
        """)
        rows = cur.fetchall()
        conn.close()

        if not rows:
            print("v_intent_docs가 비었습니다.")
            return

        # 기존 문서 삭제
        try:
            existing = self.unified_collection.get()
            if existing.get("ids"):
                self.unified_collection.delete(ids=existing["ids"])
        except Exception as e:
            print("통합 컬렉션 초기화 실패:", e)

        documents, metadatas, ids = [], [], []

        for r in rows:
            intent_id = r["intent_id"]
            intent = (r["intent"] or "").strip()
            fkey = (r["function_key"] or "").strip()
            fname = (r["function_name"] or "").strip()
            help_trim = (r["help_text"] or "")[:700]  # 길이 튜닝 지점

            # 1) SHORT
            aliases = guess_aliases(intent, fkey)
            doc_short = (
                f"의도: {intent}\n"
                f"함수키: {fkey}\n"
                f"별칭: {', '.join(aliases)}\n"
                f"핵심: {short_hint_from_help(help_trim, intent)}"
            )
            documents.append(doc_short)
            metadatas.append({
                "type": "intent",
                "intent": intent,
                "function_key": fkey,
                "function_name": fname,
                "view": "SHORT",
            })
            ids.append(f"intent_{intent_id}_short")

            # 2) DESC
            desc = make_one_liner_description(intent, help_trim)
            doc_desc = f"의도: {intent}\n설명: {desc}"
            documents.append(doc_desc)
            metadatas.append({
                "type": "intent",
                "intent": intent,
                "function_key": fkey,
                "function_name": fname,
                "view": "DESC",
            })
            ids.append(f"intent_{intent_id}_desc")

            # 3) HELP
            doc_help = f"도움말: {help_trim}"
            documents.append(doc_help)
            metadatas.append({
                "type": "intent",
                "intent": intent,
                "function_key": fkey,
                "function_name": fname,
                "view": "HELP",
            })
            ids.append(f"intent_{intent_id}_help")

        # 배치 add
        self.unified_collection.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids
        )
        print(f"[임베딩 완료] 의도 {len(rows)}건 → 문서 {len(ids)}건(뷰 3배) 추가")

    def find_best_intent(
        self,
        query: str,
        top_k: int = 30,
        metric: str = "cosine",
        threshold: float = DEFAULT_THRESHOLD,
    ) -> Dict[str, Any]:
        """
        1) 문서 단위 검색(뷰 섞임)
        2) 뷰 가중치 적용
        3) intent 단위로 집계 (max + bonus*(sum-max))
        4) 최종 intent 1개(또는 상위 N개) 반환
        """
        if not self.unified_collection:
            return {"ok": False, "message": "unified_collection not initialized"}
        if not query:
            return {"ok": False, "message": "empty query"}

        res = self.unified_collection.query(
            query_texts=[query],
            n_results=top_k,
            include=["distances", "metadatas", "documents"],
        )

        distances = (res.get("distances") or [[]])[0]
        metadatas = (res.get("metadatas") or [[]])[0]
        ids = (res.get("ids") or [[]])[0]
        documents = (res.get("documents") or [[]])[0]

        if not metadatas:
            return {"ok": False, "message": "no hits"}

        # 1) 문서 점수 계산(거리→유사도), 뷰 가중치 적용
        scored_docs: List[Dict[str, Any]] = []
        for d, m, i, doc in zip(distances, metadatas, ids, documents):
            if m.get("type") != "intent":
                continue
            view = m.get("view", "HELP")
            base_sim = _to_similarity(d, metric=metric)
            weight = VIEW_WEIGHT.get(view, 0.5)
            sim = base_sim * weight
            scored_docs.append({
                "id": i,
                "intent": m.get("intent", ""),
                "function_key": m.get("function_key", ""),
                "view": view,
                "base_sim": base_sim,
                "weight": weight,
                "sim": sim,
                "doc": doc,
            })

        if not scored_docs:
            return {"ok": False, "message": "no intent-type hits"}

        # 2) intent 단위로 집계
        agg = defaultdict(lambda: {
            "score_max": 0.0,
            "score_sum": 0.0,
            "hits": 0,
            "function_key": None,
            "views": set(),
            "samples": [],
        })

        for s in scored_docs:
            key = (s["intent"], s["function_key"])
            bucket = agg[key]
            bucket["score_max"] = max(bucket["score_max"], s["sim"])
            bucket["score_sum"] += s["sim"]
            bucket["hits"] += 1
            bucket["function_key"] = s["function_key"]
            if s["view"]:
                bucket["views"].add(s["view"])
            if len(bucket["samples"]) < 3:
                bucket["samples"].append(s)

        # 3) 최종 스코어 계산: max + bonus*(sum-max)
        finals: List[Dict[str, Any]] = []
        for (intent, fkey), v in agg.items():
            score_max = v["score_max"]
            score_sum = v["score_sum"]
            final_score = score_max + FUSION_BONUS * max(0.0, (score_sum - score_max))
            finals.append({
                "intent": intent,
                "function_key": fkey,
                "score": final_score,
                "views": sorted(v["views"]),
                "hits": v["hits"],
                "samples": v["samples"],
            })

        finals.sort(key=lambda x: x["score"], reverse=True)
        top = finals[0] if finals else None
        if not top:
            return {"ok": False, "message": "no intent candidate"}

        status = "ok" if top["score"] >= threshold else "low_confidence"

        return {
            "ok": True,
            "status": status,
            "query": query,
            "top_intent": {
                "intent": top["intent"],
                "function_key": top["function_key"],
                "score": round(top["score"], 4),
            },
            "candidates": [
                {
                    "intent": c["intent"],
                    "function_key": c["function_key"],
                    "score": round(c["score"], 4),
                    "views": c["views"],
                }
                for c in finals[:5]
            ],
            "debug": {
                "threshold": threshold,
                "view_weight": VIEW_WEIGHT,
                "fusion_bonus": FUSION_BONUS,
                "top_samples": [
                    {
                        "view": s["view"],
                        "sim": round(s["sim"], 4),
                        "base_sim": round(s["base_sim"], 4),
                        "id": s["id"],
                    }
                    for s in (top.get("samples") or [])
                ],
            },
        }


    def search_intent(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """
        기존 시그니처 유지용 래퍼.
        내부적으로 late fusion을 사용해 최상위 intent 1개 + 후보 반환 형식을 맞춘다.
        """
        res = self.find_best_intent(query=query, top_k=max(30, n_results * 6))
        if not res.get("ok"):
            return []

        # 구 형식과 호환되는 간단 리스트로 축약 (원하면 그대로 res 반환해도 됨)
        out = []
        if res.get("top_intent"):
            ti = res["top_intent"]
            out.append({
                "metadata": {
                    "type": "intent",
                    "intent": ti["intent"],
                    "function_key": ti["function_key"],
                },
                "similarity": ti["score"],
            })
        # 후보 추가
        for c in (res.get("candidates") or [])[1:n_results]:
            out.append({
                "metadata": {
                    "type": "intent",
                    "intent": c["intent"],
                    "function_key": c["function_key"],
                },
                "similarity": c["score"],
            })
        return out

    def search_by_collection(self, query: str, collection_name: str = "intents", n_results: int = 5):
        """특정 컬렉션에서 검색합니다."""
        collection_attr = f"{collection_name}_collection"
        if not hasattr(self, collection_attr) or getattr(self, collection_attr) is None:
            print(f"{collection_name} 컬렉션이 초기화되지 않았습니다.")
            return []

        try:
            collection = getattr(self, collection_attr)
            results = collection.query(
                query_texts=[query],
                n_results=n_results,
                include=['metadatas', 'distances']
            )

            return [
                {
                    "metadata": metadata,
                    "distance": distance
                }
                for metadata, distance in zip(results['metadatas'][0], results['distances'][0])
            ]
        except Exception as e:
            print(f"{collection_name} 컬렉션 검색 중 오류 발생: {e}")
            return []

    def embed_all_data(self):
        """모든 테이블의 데이터를 임베딩합니다."""
        print("데이터 임베딩을 시작합니다...")
        self.load_and_embed_unified_intents()
        print("모든 데이터 임베딩이 완료되었습니다.")

# 사용 예시 함수
def create_embedding_instance():
    """임베딩 인스턴스를 생성하고 데이터를 로드합니다."""
    embedding_db = ChromaDBEmbedding()
    embedding_db.embed_all_data()
    return embedding_db

def search_intent_from_query(query: str, embedding_db: ChromaDBEmbedding = None):
    """사용자 쿼리로부터 intent를 검색합니다."""
    if embedding_db is None:
        embedding_db = ChromaDBEmbedding()

    results = embedding_db.search_intent(query)
    return results
