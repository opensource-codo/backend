# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the server (requires .env with OPENAI_API_KEY)
uvicorn main:app --reload
# or
python main.py

# Build ChromaDB vector index (run once or after DB changes)
python services/build_embed_chroma.py

# Run all tests
python -m pytest test/ -v

# Run a single test file
python -m pytest test/test_chroma_pipeline_real.py -v
```

**Environment:** Create `.env` in project root with `OPENAI_API_KEY=...`

## Architecture

CODO Backend is a **Windows assistant API** that maps natural language user input to Windows system actions. The core pipeline:

```
User Text → RAG Intent Search → Function Mapping → Param Extraction → Validation → Action Plan
```

### Request Lifecycle (`POST /api/v1/userInputRe/`)

1. **Intent Recognition** — ChromaDB vector search (cosine similarity, late fusion scoring across SHORT/DESC/HELP document views). Falls back to OpenAI LLM if confidence < 0.28.
2. **Function Mapping** — Matches intent → `function_key` → fetches function metadata from SQLite.
3. **Method Routing:**
   - `GUIDE` mode → `guide_service.py` generates human-readable UI instructions.
   - `EXECUTION` mode → param extraction + validation + action planning.
4. **Parameter Extraction** — OpenAI function calling (`gpt-4o-mini`) extracts params from user text; rule-based fallback handles Windows path patterns.
5. **Stateful Interaction** — If params are missing or the action is risky, a session is created (15-min TTL, in-memory) and the response signals `info_required` or `confirm_required`. Client resumes at `/continue` or `/confirm`.
6. **Action Planning** — Registry-based planners (copy_file, delete_file, etc.) or generic DB template planner generate an execution spec (`shell` / `hotkey`).

### Key Files

| File | Role |
|------|------|
| [api/v1/endpoints/user_input_re.py](api/v1/endpoints/user_input_re.py) | Main orchestrator — routes all 3 endpoints |
| [services/intent_service.py](services/intent_service.py) | RAG + LLM intent extraction entry point |
| [services/search_chroma.py](services/search_chroma.py) | ChromaDB queries + late fusion scoring |
| [services/validator_service.py](services/validator_service.py) | Schema-driven param validation and type coercion |
| [services/executor_service.py](services/executor_service.py) | Action planning registry |
| [services/param_extractor.py](services/param_extractor.py) | OpenAI function calling for param extraction |
| [services/interaction_store.py](services/interaction_store.py) | In-memory session state (15-min TTL) |
| [services/build_embed_chroma.py](services/build_embed_chroma.py) | Embedding pipeline: SQLite view → ChromaDB |
| [db/database.py](db/database.py) | SQLite connection utilities |
| [core/config.py](core/config.py) | Pydantic settings (API keys, DB path, log config) |

### Storage

- **SQLite (`assistant.db`)** — Source of truth for functions, intents, parameters.
  - Key tables: `functions`, `intents`, `intent_param`, `help_contents`
  - Key views: `v_intent_materialized` (used for embedding), `v_intent_docs`
- **ChromaDB (`./chroma_db/`)** — Persistent HNSW vector index.
  - Primary collection: `intents` (3 document views per intent: SHORT, DESC, HELP with weights 1.0/0.7/0.4)

### Parameter Type System (`validator_service.py`)

Supported types: `path`, `bool`, `enum`, `str`. Validation includes:
- Windows path normalization (backslash, UNC)
- Bool synonym mapping (켜/끄/true/false/yes/no)
- Command injection blocking (`&&`, `||`, `|`, `;`, `` ` ``, `$`, `<`, `>`)
- Cross-field conflict checks (e.g., src ≠ dst)

### Action Planning (`executor_service.py`)

Returns an execution spec JSON: `{ version, kind: "shell"|"hotkey", payload: {...} }`.
Risk classification patterns trigger `caution`/`danger` levels requiring user confirmation before execution.

### API Endpoints

| Route | Purpose |
|-------|---------|
| `POST /api/v1/userInputRe/` | Main: text → intent → execution plan |
| `POST /api/v1/userInputRe/continue` | Supplement missing parameters |
| `POST /api/v1/userInputRe/confirm` | Confirm risky operation |
| `GET /api/v1/guide/{function_key}` | Fetch UI guidance for a function |
