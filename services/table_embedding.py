import chromadb
from chromadb.config import Settings
import sqlite3
from typing import List, Dict, Any, Optional
import os
import numpy as np
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")

# OpenAI 클라이언트 초기화
openai_client = OpenAI(api_key=api_key)


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

    def load_and_embed_intents(self):
        """intents 테이블의 데이터를 로드하고 임베딩합니다."""
        if not self.intents_collection:
            print("intents 컬렉션이 초기화되지 않았습니다.")
            return
            
        conn = self.get_db_connection()
        cursor = conn.execute("""
            SELECT i.id, i.intent, i.function_id, 
                   f.function_key, f.function_name, f.shortcut,
                   hc.help_text
            FROM intents i
            LEFT JOIN functions f ON i.function_id = f.id
            LEFT JOIN help_contents hc ON i.id = hc.intent_id
        """)
        
        intents_data = cursor.fetchall()
        conn.close()
        
        if not intents_data:
            print("intents 테이블에 데이터가 없습니다.")
            return
        
        # 기존 데이터 삭제
        try:
            # 모든 문서를 가져와서 ID로 삭제
            existing_data = self.intents_collection.get()
            if existing_data['ids']:
                self.intents_collection.delete(ids=existing_data['ids'])
        except Exception as e:
            print(f"기존 intents 데이터 삭제 실패: {e}")
            return
        
        documents = []
        metadatas = []
        ids = []
        
        for row in intents_data:
            # 검색용 텍스트 구성 (도움말 정보도 포함)
            search_text = f"의도: {row['intent']}"
            if row['function_name']:
                search_text += f" 함수: {row['function_name']}"
            if row['shortcut']:
                search_text += f" 단축키: {row['shortcut']}"
            if row['help_text']:
                search_text += f" 도움말: {row['help_text']}"
            
            documents.append(search_text)
            metadatas.append({
                "intent": row['intent'] or "",
                "function_id": str(row['function_id']) if row['function_id'] else "",
                "function_key": row['function_key'] or "",
                "function_name": row['function_name'] or "",
                "shortcut": row['shortcut'] or "",
                "help_text": row['help_text'] or "",
                "type": "intent"
            })
            ids.append(f"intent_{row['id']}")
        
        # ChromaDB에 추가
        self.intents_collection.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids
        )
        
        print(f"{len(intents_data)}개의 intent 데이터가 임베딩되었습니다.")
    
    def load_and_embed_functions(self):
        """functions 테이블의 데이터를 로드하고 임베딩합니다."""
        if not self.functions_collection:
            print("functions 컬렉션이 초기화되지 않았습니다.")
            return
            
        conn = self.get_db_connection()
        cursor = conn.execute("""
            SELECT id, function_key, function_name, script_path, shortcut, script_command
            FROM functions
        """)
        
        functions_data = cursor.fetchall()
        conn.close()
        
        if not functions_data:
            print("functions 테이블에 데이터가 없습니다.")
            return
        
        # 기존 데이터 삭제
        try:
            # 모든 문서를 가져와서 ID로 삭제
            existing_data = self.functions_collection.get()
            if existing_data['ids']:
                self.functions_collection.delete(ids=existing_data['ids'])
        except Exception as e:
            print(f"기존 functions 데이터 삭제 실패: {e}")
            return
        
        documents = []
        metadatas = []
        ids = []
        
        for row in functions_data:
            # 검색용 텍스트 구성
            search_text = f"함수: {row['function_name']}"
            if row['function_key']:
                search_text += f" 키: {row['function_key']}"
            if row['shortcut']:
                search_text += f" 단축키: {row['shortcut']}"
            if row['script_command']:
                search_text += f" 명령어: {row['script_command']}"
            
            documents.append(search_text)
            metadatas.append({
                "function_key": row['function_key'] or "",
                "function_name": row['function_name'] or "",
                "script_path": row['script_path'] or "",
                "shortcut": row['shortcut'] or "",
                "script_command": row['script_command'] or "",
                "type": "function"
            })
            ids.append(f"function_{row['id']}")
        
        # ChromaDB에 추가
        self.functions_collection.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids
        )
        
        print(f"{len(functions_data)}개의 function 데이터가 임베딩되었습니다.")
    
    def load_and_embed_help_contents(self):
        """help_contents 테이블의 데이터를 로드하고 임베딩합니다."""
        if not self.help_contents_collection:
            print("help_contents 컬렉션이 초기화되지 않았습니다.")
            return
            
        conn = self.get_db_connection()
        cursor = conn.execute("""
            SELECT hc.id, hc.help_text, hc.intent_id, i.intent
            FROM help_contents hc
            LEFT JOIN intents i ON hc.intent_id = i.id
        """)
        
        help_data = cursor.fetchall()
        conn.close()
        
        if not help_data:
            print("help_contents 테이블에 데이터가 없습니다.")
            return
        
        # 기존 데이터 삭제
        try:
            # 모든 문서를 가져와서 ID로 삭제
            existing_data = self.help_contents_collection.get()
            if existing_data['ids']:
                self.help_contents_collection.delete(ids=existing_data['ids'])
        except Exception as e:
            print(f"기존 help_contents 데이터 삭제 실패: {e}")
            return
        
        documents = []
        metadatas = []
        ids = []
        
        for row in help_data:
            # 검색용 텍스트 구성
            search_text = f"도움말: {row['help_text']}"
            if row['intent']:
                search_text += f" 의도: {row['intent']}"
            
            documents.append(search_text)
            metadatas.append({
                "help_text": row['help_text'] or "",
                "intent_id": str(row['intent_id']) if row['intent_id'] else "",
                "intent": row['intent'] or "",
                "type": "help_content"
            })
            ids.append(f"help_{row['id']}")
        
        # ChromaDB에 추가
        self.help_contents_collection.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids
        )
        
        print(f"{len(help_data)}개의 help_content 데이터가 임베딩되었습니다.")
    
    def create_unified_collection(self):
        """모든 데이터를 통합한 검색용 컬렉션을 생성합니다."""
        if not self.unified_collection:
            print("unified_collection이 초기화되지 않았습니다.")
            return
            
        # 기존 통합 컬렉션 삭제 - ChromaDB에서는 where={} 대신 다른 방법 사용
        try:
            # 모든 문서를 가져와서 ID로 삭제
            existing_data = self.unified_collection.get()
            if existing_data['ids']:
                self.unified_collection.delete(ids=existing_data['ids'])
        except Exception as e:
            print(f"기존 통합 컬렉션 데이터 삭제 실패: {e}")
            return
        
        # intents 데이터 추가
        intents_results = self.intents_collection.get()
        if intents_results['documents']:
            self.unified_collection.add(
                documents=intents_results['documents'],
                metadatas=intents_results['metadatas'],
                ids=intents_results['ids']
            )
        
        # functions 데이터 추가
        functions_results = self.functions_collection.get()
        if functions_results['documents']:
            self.unified_collection.add(
                documents=functions_results['documents'],
                metadatas=functions_results['metadatas'],
                ids=functions_results['ids']
            )
        
        # help_contents 데이터 추가
        help_results = self.help_contents_collection.get()
        if help_results['documents']:
            self.unified_collection.add(
                documents=help_results['documents'],
                metadatas=help_results['metadatas'],
                ids=help_results['ids']
            )
        
        print("통합 검색 컬렉션이 생성되었습니다.")
    
    def load_and_embed_unified_intents(self):
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
            # 도움말이 너무 길어 의도를 덮어쓰지 않도록 적당히 자르거나(예: 800자) 요약/키워드만 포함 추천
            help_trim = (r["help_text"] or "")[:800]

            # 한 문서 = 한 의도
            doc = (
                f"의도: {r['intent']}\n"
                f"함수 설명: {r['function_name'] or ''}\n"
                f"함수명: {r['function_key'] or ''}\n"
                f"도움말: {help_trim}"
            )
            documents.append(doc)
            metadatas.append({
                "type": "intent",
                "intent": r["intent"] or "",
                "function_key": r["function_key"] or "",
                "function_name": r["function_name"] or "",
            })
            ids.append(f"intent_{r['intent_id']}")

        self.unified_collection.add(
            documents=documents, 
            metadatas=metadatas, 
            ids=ids)
        print(f"통합 의도 {len(rows)}건 임베딩 완료")

    
    def search_intent(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """사용자 입력에 대해 가장 유사한 intent를 검색합니다."""
        if not self.unified_collection:
            print("unified_collection이 초기화되지 않았습니다.")
            return []
            
        try:
            results = self.unified_collection.query(
                query_texts=[query],
                n_results=max(n_results*3, n_results),
                include=['metadatas', 'distances']
            )
            
            pairs = [
                {"metadata": m, "distance": d, "similarity": 1.0 - float(d)}
                for m, d in zip(results['metadatas'][0], results['distances'][0])
                if m.get("type") == "intent"  # 통합에서 intent만 남기기
            ]
            return [p for p in pairs if p["similarity"] >= 0.0][:n_results]
        
        except Exception as e:
            print(f"검색 중 오류 발생: {e}")
            return []
    
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
        
        # self.load_and_embed_intents()
        # self.load_and_embed_functions()
        # self.load_and_embed_help_contents()
        # self.create_unified_collection()
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