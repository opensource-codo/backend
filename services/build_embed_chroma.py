# build_embed_chroma.py
import os, sqlite3, math
os.environ["CHROMADB_DEFAULT_EMBEDDING_FUNCTION"] = "none"  
from typing import Dict, List
from dotenv import load_dotenv
from openai import OpenAI
import chromadb

EMBED_MODEL = "text-embedding-3-small"

VIEW_WEIGHT = {"SHORT": 1.0, "DESC": 0.7, "HELP": 0.4}

def connect_db(path=None):
    # Use APP_DB_PATH if provided; default to assistant.db
    db_path = path or os.getenv("APP_DB_PATH", "assistant.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def load_aliases(conn) -> Dict[str, List[str]]:
    try:
        rows = conn.execute("SELECT function_key, alias FROM intent_aliases").fetchall()
    except sqlite3.OperationalError:
        return {}
    m: Dict[str, List[str]] = {}
    for r in rows:
        m.setdefault(r["function_key"], []).append(r["alias"])
    return m

def build_text_views(row: sqlite3.Row, aliases_map: Dict[str, List[str]]):
    key = row["function_key"]
    intent = (row["intent_text"] or "").strip()
    fn = (row["function_name"] or "").strip()
    shortcut = (row["shortcut"] or "").strip()
    script_cmd = (row["script_command"] or "").strip()
    help_text = (row["help_text"] or "").strip()

    alias_list = aliases_map.get(key, [])
    alias_str = ", ".join(alias_list) if alias_list else ""

    short_text = intent
    if alias_str:
        short_text += f" | 동의어: {alias_str}"

    desc_text = fn if fn else intent
    if shortcut:
        desc_text += f". 단축키: {shortcut}"
    if script_cmd:
        desc_text += f". 명령: {script_cmd}"
    if not desc_text.endswith("."):
        desc_text += "."

    return {
        "SHORT": short_text.strip(),
        "DESC": desc_text.strip(),
        "HELP": help_text.strip(),
    }

def chunk(lst, size):
    for i in range(0, len(lst), size):
        yield lst[i:i+size]

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

    # 2) 문서 생성
    docs, metas, ids = [], [], []
    seen_ids = set()
    for r in rows:
        views = build_text_views(r, aliases)
        for view_name, text in views.items():
            if not text:
                continue
            fid = r["function_key"]
            doc_id = f"{fid}::{view_name}"
            if doc_id in seen_ids:
                continue
            seen_ids.add(doc_id)
            docs.append(text)
            metas.append({
                "function_key": fid,
                "intent": r["intent_text"],
                "view": view_name,
                "shortcut": r["shortcut"],
                "weight": VIEW_WEIGHT[view_name],
            })
            ids.append(doc_id)

    if not docs:
        print("No docs to embed")
        return
    
    # 3) 임베딩 생성 (배치)
    print("3) 임베딩 생성")
    vectors = []
    BATCH = 128
    for batch_texts in chunk(docs, BATCH):
        resp = openai.embeddings.create(model=EMBED_MODEL, input=batch_texts)
        vectors.extend([d.embedding for d in resp.data])

    assert len(vectors) == len(docs)

    # 4) Chroma 업서트
    print("4) Chroma 업서트")
    client = chromadb.PersistentClient(path="./chroma_db")
    # cosine 공간 사용(기본값도 괜찮지만 명시)
    print("get_or_create_collection 실행")
    collection = client.get_or_create_collection(
        name="intents",
        metadata={"hnsw:space": "cosine"}
    )
    print("upsert 실행")
    collection.upsert(
        ids=ids,
        documents=docs,
        metadatas=metas,
        embeddings=vectors
    )
    print(f"Upserted {len(ids)} docs into Chroma collection 'intents'.")

if __name__ == "__main__":
    main()
