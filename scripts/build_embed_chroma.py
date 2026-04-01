# build_embed_chroma.py
import os, sqlite3, re
os.environ["CHROMADB_DEFAULT_EMBEDDING_FUNCTION"] = "none"
from typing import Dict, List
from dotenv import load_dotenv
from openai import OpenAI
import chromadb

EMBED_MODEL = "text-embedding-3-small"
VIEW_WEIGHT = {"SHORT": 1.0, "DESC": 0.7, "HELP": 0.4}
BATCH = 128
HELP_MAX_LEN = 700


def connect_db(path=None):
    db_path = path or os.getenv("APP_DB_PATH", "assistant.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def load_aliases(conn) -> Dict[str, List[str]]:
    """DB intent_aliases 테이블에서 alias 로드."""
    try:
        rows = conn.execute("SELECT function_key, alias FROM intent_aliases").fetchall()
    except sqlite3.OperationalError:
        return {}
    m: Dict[str, List[str]] = {}
    for r in rows:
        m.setdefault(r["function_key"], []).append(r["alias"])
    return m


def guess_aliases(intent: str, function_key: str) -> List[str]:
    """규칙 기반 동의어 자동 생성."""
    intent = (intent or "").strip()
    fkey = (function_key or "").strip()

    aliases: set = set()
    if fkey:
        aliases.add(fkey)
        parts = re.split(r"[_\-]+", fkey)
        if len(parts) > 1:
            aliases.add(" ".join(parts))

    if any(k in intent for k in ["삭제", "지우", "제거"]) or "delete" in fkey:
        aliases.update(["파일 삭제", "파일 제거", "파일 지우기", "delete file", "del", "Shift+Delete", "휴지통", "영구 삭제"])
    if any(k in intent for k in ["붙여넣", "paste"]) or "paste" in fkey:
        aliases.update(["파일 붙여넣기", "paste file", "Ctrl+V"])
    if any(k in intent for k in ["복사", "copy"]) or "copy" in fkey:
        aliases.update(["파일 복사", "copy file", "Ctrl+C"])
    if any(k in intent for k in ["잘라내", "자르기", "cut"]) or "cut" in fkey:
        aliases.update(["파일 잘라내기", "cut file", "Ctrl+X"])
    if any(k in intent for k in ["변경", "이름", "rename"]) or "rename" in fkey:
        aliases.update(["파일 이름 변경", "rename file", "F12"])
    if any(k in intent for k in ["제어판", "control panel"]) or "control_panel" in fkey:
        aliases.update(["제어판", "Control Panel", "컨트롤 패널"])
    if any(k in intent for k in ["캡처", "스크린샷", "screenshot"]) or "screenshot" in fkey:
        aliases.update(["스크린샷", "캡처", "PrintScreen", "screenshot", "PrtSc", "Win+Shift+S", "스니핑툴"])
    if any(k in intent for k in ["재시작", "restart"]) or "restart" in fkey:
        aliases.update(["재시작", "다시 시작", "restart"])
    if any(k in intent for k in ["종료", "끄기", "shutdown"]) or "shutdown" in fkey:
        aliases.update(["종료", "shutdown", "전원 끄기"])

    return sorted(aliases)


def _first_sentence(text: str, max_len: int = 120) -> str:
    if not text:
        return ""
    s = re.split(r"[.!?。\n]", text.strip())[0].strip()
    return s[:max_len]


def build_text_views(row: sqlite3.Row, aliases_map: Dict[str, List[str]]) -> Dict[str, str]:
    key = row["function_key"]
    intent = (row["intent_text"] or "").strip()
    fn = (row["function_name"] or "").strip()
    shortcut = (row["shortcut"] or "").strip()
    script_cmd = (row["script_command"] or "").strip()
    help_text = (row["help_text"] or "").strip()
    help_trim = help_text[:HELP_MAX_LEN]

    # DB alias + 규칙 기반 alias 합산
    db_aliases = aliases_map.get(key, [])
    rule_aliases = guess_aliases(intent, key)
    all_aliases = sorted(set(db_aliases) | set(rule_aliases))
    alias_str = ", ".join(all_aliases)

    # SHORT: 구조화된 레이블 형식 (의미 검색 정확도 향상)
    short_hint = _first_sentence(help_trim, max_len=100) or intent
    short_text = (
        f"의도: {intent}\n"
        f"함수키: {key}\n"
        f"별칭: {alias_str}\n"
        f"핵심: {short_hint}"
    )

    # DESC: 기능 설명 + 단축키/명령 정보
    desc_base = fn if fn else _first_sentence(help_trim, 140) or intent
    if shortcut:
        desc_base += f". 단축키: {shortcut}"
    if script_cmd:
        desc_base += f". 명령: {script_cmd}"
    if not desc_base.endswith("."):
        desc_base += "."
    desc_text = f"의도: {intent}\n설명: {desc_base}"

    # HELP: 700자 제한으로 노이즈 감소
    help_doc = f"도움말: {help_trim}" if help_trim else ""

    return {
        "SHORT": short_text.strip(),
        "DESC": desc_text.strip(),
        "HELP": help_doc.strip(),
    }


def chunk(lst, size):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]


def main():
    print("build_embed_chroma.py 실행")
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    openai = OpenAI(api_key=api_key)

    # 1) DB 로드
    conn = connect_db()
    aliases = load_aliases(conn)
    rows = conn.execute("SELECT * FROM v_intent_materialized").fetchall()
    conn.close()

    # 2) 문서 생성
    docs, metas, ids = [], [], []
    seen_ids = set()
    for r in rows:
        views = build_text_views(r, aliases)
        for view_name, text in views.items():
            if not text:
                continue
            doc_id = f"{r['function_key']}::{view_name}"
            if doc_id in seen_ids:
                continue
            seen_ids.add(doc_id)
            docs.append(text)
            metas.append({
                "function_key": r["function_key"],
                "intent": r["intent_text"],
                "view": view_name,
                "shortcut": r["shortcut"] or "",
                "weight": VIEW_WEIGHT[view_name],
            })
            ids.append(doc_id)

    if not docs:
        print("No docs to embed")
        return

    # 3) OpenAI 임베딩 생성 (배치)
    print(f"3) 임베딩 생성 — {len(docs)}건")
    vectors = []
    for batch_texts in chunk(docs, BATCH):
        resp = openai.embeddings.create(model=EMBED_MODEL, input=batch_texts)
        vectors.extend([d.embedding for d in resp.data])

    assert len(vectors) == len(docs)

    # 4) Chroma upsert
    print("4) Chroma upsert")
    client = chromadb.PersistentClient(path="./chroma_db")
    collection = client.get_or_create_collection(
        name="intents",
        metadata={"hnsw:space": "cosine"}
    )
    collection.upsert(
        ids=ids,
        documents=docs,
        metadatas=metas,
        embeddings=vectors,
    )
    print(f"Upserted {len(ids)} docs into 'intents' collection.")


if __name__ == "__main__":
    main()
