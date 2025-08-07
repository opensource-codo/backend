# Intent Analysis API with RAG

사용자 입력을 분석하여 의도(intent)를 파악하고 적절한 함수를 실행하는 API 서버입니다. ChromaDB를 활용한 RAG(Retrieval-Augmented Generation) 시스템을 통해 더 정확한 intent 분석을 제공합니다.

## 주요 기능

- **RAG 기반 Intent 분석**: ChromaDB를 사용하여 사용자 입력과 유사한 intent를 검색
- **함수 실행**: intent에 해당하는 함수를 실행
- **가이드 제공**: 사용자에게 적절한 가이드를 제공
- **실시간 검색**: 유사한 intent들을 실시간으로 검색

## 설치 및 실행

### 1. 의존성 설치
```bash
pip install -r requirements.txt
```

### 2. 환경 변수 설정
`.env` 파일을 생성하고 다음 내용을 추가하세요:
```
OPENAI_API_KEY=your_openai_api_key_here
```

### 3. 데이터베이스 임베딩
ChromaDB에 데이터를 임베딩합니다:
```bash
python test_embedding.py
```

또는 API를 통해 임베딩:
```bash
curl -X POST "http://localhost:8000/api/v1/embed"
```

### 4. 서버 실행
```bash
uvicorn main:app --reload
```

## API 엔드포인트

### 1. 사용자 입력 처리
```
POST /api/v1/
```
사용자 입력을 받아 intent를 분석하고 적절한 응답을 반환합니다.

### 2. 유사한 Intent 검색
```
POST /api/v1/search
```
사용자 입력과 유사한 intent들을 검색합니다.

### 3. 데이터베이스 임베딩
```
POST /api/v1/embed
```
데이터베이스의 모든 데이터를 ChromaDB에 임베딩합니다.

## 데이터베이스 구조

### functions 테이블
- `id`: 기본 키
- `function_key`: 함수 키
- `function_name`: 함수 이름
- `script_path`: 스크립트 경로
- `shortcut`: 단축키
- `script_command`: 스크립트 명령어

### intents 테이블
- `id`: 기본 키
- `intent`: 사용자 의도
- `function_id`: 연결된 함수 ID

### help_contents 테이블
- `id`: 기본 키
- `intent_id`: 연결된 intent ID
- `help_text`: 도움말 텍스트

## RAG 시스템

### ChromaDB 임베딩
- `services/table_embedding.py`: ChromaDB 임베딩 클래스
- OpenAI Embedding API 사용
- 통합 검색 컬렉션 제공

### 검색 기능
- 유사도 기반 검색
- 컬렉션별 검색 지원
- 실시간 검색 결과 제공

## 테스트

임베딩 기능을 테스트하려면:
```bash
python test_embedding.py
```

## 주요 파일 구조

```
app/
├── api/v1/endpoints/user_input.py  # API 엔드포인트
├── services/intent_service.py       # Intent 분석 서비스 (RAG 포함)
├── services/table_embedding.py     # ChromaDB 임베딩 클래스
├── db/database.py                  # 데이터베이스 연결
├── test_embedding.py               # 임베딩 테스트 스크립트
└── requirements.txt                # 의존성 목록
```