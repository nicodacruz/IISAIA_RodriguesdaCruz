# NotarIA — contexto completo para Claude Code

## Qué es este proyecto

Sistema de IA para escribanías argentinas. Ingesta escrituras públicas (PDF/DOC), extrae
metadata estructurada, responde consultas en lenguaje natural (SQL + RAG), permite consultas
jurídicas sobre normativa argentina (CCC, Ley 404, Ley 17.801) y genera documentos DOCX
desde plantillas legales.

**Dos objetivos en paralelo:**
1. Trabajo Final — Especialización en IA FIUBA, entrega diciembre 2026
2. Producto SaaS vendible a escribanías argentinas (B2B)

**Prioridades al tomar decisiones:**
1. Confianza y trazabilidad
2. Confidencialidad y aislamiento por cliente
3. Simplicidad operacional
4. Mantenibilidad y extensibilidad
5. Viabilidad comercial para escribanías argentinas

---

## Reglas que nunca se rompen

- **Nunca hardcodear secretos.** Sin API keys ni tokens en código fuente. Siempre variables de entorno.
- **`src/` no se reescribe arquitecturalmente.** Es la lógica de negocio del producto. Se extiende y corrige, nunca se reemplaza.
- **Los YAML son la fuente de verdad del dominio.** `config/casos.yaml`, `config/escrituras_config.yaml`, `config/llm.yaml`. Antes de tocarlos, validar con `python scripts/validate_config.py`.
- **Cambios en `src/core/router.py` o `src/analytics/` requieren pasar los tests.** Correr `pytest tests/ -x -q` antes de continuar.
- **Sin cambios de arquitectura no acordados.** Si algo requiere un cambio estructural, detenerse, explicar el trade-off, y esperar confirmación.
- **Los datos reales son confidenciales.** Nunca loggear contenido de escrituras en texto plano. Solo IDs en los logs de auditoría.

---

## Stack actual — estado real al 2026-05-21

| Capa | Tecnología | Estado |
|---|---|---|
| Frontend | Next.js 15 (App Router) + shadcn/ui | Construido, corriendo en localhost:3000 |
| Backend | FastAPI + asyncpg | Construido, corriendo en localhost:8000 |
| Base de datos | Supabase (Postgres + pgvector) | Schema creado, pendiente conectar en prod |
| Auth | Clerk (JWT) | Configurado; dev-mode si no hay `CLERK_SECRET_KEY` |
| LLM (cloud) | OpenAI gpt-4o-mini | Activo (configurable en `config/llm.yaml`) |
| LLM (local) | Ollama qwen3:14b | Opcional; activo cuando `LLM_BACKEND=local\|hybrid` |
| Embeddings | OpenAI text-embedding-3-small (1536d) / multilingual-e5-large-instruct via Ollama | Activo; controlado por `EMBEDDINGS_BACKEND` |
| RAG vectorial | pgvector (Supabase) | Activo; escrituras en `embeddings`, normativa en `legal_embeddings` |
| Metadata SQL | SQLite (local) / Postgres (cloud) | Auto-selección via `DATABASE_URL` env |
| Doc generation | Jinja2 + python-docx | Activo, data-driven desde YAML |
| Docker | docker-compose.yml + Dockerfiles | Creado, no probado en CI aún |
| Deploy | Sin deploy en producción aún | Pendiente Railway/Fly.io (backend) + Vercel (frontend) |

---

## Arquitectura — cómo fluye una consulta

```
Usuario (Next.js)
    │ POST /chat {message, conversation_id?}
    ▼
backend/routers/chat.py
    │ require_auth() → user_id via Clerk o dev-mode
    │ Restaura gen_state desde conversations.gen_state (JSONB) si sesión activa
    ▼
src/core/router.py :: ask_unified()
    │
    ├─ src/core/intent_classifier.py :: classify_intent_llm()
    │      └─ src/core/llm_client.py :: get_client_for_use_case("intent_classifier")
    │             LLM_BACKEND=hybrid → OpenAI para clasificación
    │             → LLMRoute: {mode, file_id?, acto_caso?, chat_intent?, confidence, ...}
    │
    ├─ mode="sql"       → src/analytics/ask_meta_sql.py → TextToSQL(Pg|SQLite)
    │                     llm_client → OpenAI (sql_generator, response_generator)
    │                     SQL con acto_caso exactos desde config/casos.yaml
    │                     → ejecuta contra DB → respuesta NL
    │
    ├─ mode="qa"        → src/rag/search.py :: query_index()
    │                     pgvector embeddings (filtrado por user_id + file_id/acto_caso)
    │                     → llm_client → local/OpenAI (rag_synthesizer)
    │                     → answer_with_context()
    │
    ├─ mode="legal_qa"  → src/rag/search.py :: query_legal_index()
    │                     pgvector legal_embeddings (sin user_id — textos públicos)
    │                     → llm_client → OpenAI (legal_qa)
    │                     → LLM con prompt de agente escribano (CCC, Ley 404, etc.)
    │                     Badge: LEX
    │
    ├─ mode="generate"  → src/generators/generators.py :: BaseConversationalManager
    │                     llm_client → local/OpenAI (doc_generator)
    │                     Conversación campo-por-campo → DOCX via Jinja2
    │
    └─ mode="chat"      → _answer_from_chat() (saludos, capacidades, ayuda)
                          gpt-4o-mini directo para intent "other"
    │
    ▼
backend/routers/chat.py
    Persiste en: conversations + messages + audit_log
    │
    ▼
ChatResponse {answer, source_type, conversation_id, message_id, extra?}
```

## Arquitectura — cómo fluye la ingesta

```
POST /ingest (PDF/DOC/DOCX) → {job_id}
    │
    └─ BackgroundTask: _run_ingest_pipeline()
           │
           ├─ src/ingest/pipeline.py :: ingest_file()
           │      1. _to_markdown() — PyMuPDF / LibreOffice
           │      2. parse_escritura_markdown() — LLM extrae metadata
           │      3. _upsert_jsonl() — actualiza metadata.jsonl
           │      4. _upsert_postgres() — upsert en tabla metadata
           │
           └─ src/rag/indexer_pg.py :: build_index()
                  5. Chunking semántico del markdown
                  6. Embeddings via EMBEDDINGS_BACKEND (openai|local)
                  7. Upsert chunks en pgvector (tabla embeddings, idempotente por SHA1)

GET /ingest/status/{job_id} → {queued|processing|done|error}
```

---

## Cliente LLM centralizado (src/core/llm_client.py)

Punto único de acceso a todos los LLMs. Evita que cada módulo instancie su propio cliente.

**Variables de entorno que controla:**

**Configuración de producción actual:** `LLM_BACKEND=openai`, `EMBEDDINGS_BACKEND=openai`. Todo pasa por OpenAI. Los modos `local` y `hybrid` son la ruta futura hacia privacidad total de datos (ver sección Roadmap).

| Variable | Valores | Efecto |
|---|---|---|
| `LLM_BACKEND` | `openai` \| `local` \| `hybrid` | **prod:** `openai`; hybrid=BACKEND_MAP por use-case |
| `LOCAL_MODEL` | nombre modelo Ollama | default `qwen3:14b` |
| `LOCAL_BASE_URL` | URL del servidor Ollama | default `http://localhost:11434/v1` |
| `LOCAL_API_KEY` | API key para Ollama (placeholder) | default `ollama` |
| `EMBEDDINGS_BACKEND` | `openai` \| `local` | **prod:** `openai`; local requiere migración de schema |
| `EMBEDDINGS_MODEL_LOCAL` | modelo Ollama para embeddings | default `qllama/multilingual-e5-large-instruct` |

**BACKEND_MAP en modo hybrid** (desarrollo local / futuro):

| Use-case | Backend |
|---|---|
| `intent_classifier` | OpenAI — precisión crítica |
| `sql_generator` | OpenAI — SQL debe ser correcto |
| `response_generator` | OpenAI |
| `legal_qa` | OpenAI — precisión jurídica |
| `chat` | OpenAI |
| `rag_synthesizer` | local (qwen3:14b) — síntesis RAG |
| `doc_generator` | local (qwen3:14b) — generación conversacional |

**Nota sobre Qwen3:** El thinking mode de Qwen3 causó tiempos de 4+ min en síntesis RAG. Los use-cases `rag_synthesizer` y `doc_generator` pasan `{"think": False}` en `extra_body`.

---

## Estructura de directorios

```
notary-ingest/
├── src/                        # Núcleo Python — NO se toca arquitecturalmente
│   ├── config_loader.py        # Cargador centralizado YAML/TXT con @lru_cache
│   ├── core/
│   │   ├── router.py           # ask_unified() — entry point principal
│   │   ├── intent_classifier.py # classify_intent_llm() → LLMRoute
│   │   └── llm_client.py       # get_client_for_use_case(), get_embedding_client()
│   ├── generators/
│   │   ├── generators.py       # UniversalGenerator + BaseConversationalManager
│   │   ├── schemas/base_schema.py # Pydantic models (TipoEscritura enum, etc.)
│   │   └── templates/*.j2      # Plantillas Jinja2 por tipo de escritura
│   ├── ingest/
│   │   ├── pipeline.py         # ingest_file() — pipeline completo para un documento
│   │   ├── extract_pdf.py      # PyMuPDF + fallbacks OCR
│   │   ├── extract_doc.py      # DOC/DOCX via LibreOffice
│   │   ├── metadata.py         # Extracción de metadata con LLM
│   │   └── utils.py            # sha1_file, etc.
│   ├── rag/
│   │   ├── indexer.py          # Helpers compartidos (embedder, chunker, metadata)
│   │   ├── indexer_pg.py       # build_index() + build_legal_index() → pgvector
│   │   ├── chunking_v2.py      # Chunking semántico
│   │   ├── search.py           # query_index() + query_legal_index() → pgvector
│   │   └── llm.py              # answer_with_context()
│   └── analytics/
│       ├── ask_meta_sql.py     # API pública: ask_metadata(). Auto-elige engine.
│       └── text_to_sql/
│           ├── database.py     # MetadataDatabase (SQLite)
│           ├── database_pg.py  # MetadataDatabasePg (Postgres)
│           ├── sql_generator.py # LLM genera SQL
│           ├── query_executor.py
│           ├── response_generator.py
│           └── main.py         # TextToSQLEngine + TextToSQLEnginePg
│
├── config/                     # Fuente de verdad del dominio — 100% data-driven
│   ├── casos.yaml              # Taxonomía: acto_clase → acto_subclase → acto_caso (60+ tipos)
│   ├── llm.yaml                # Modelos, temperaturas, timeouts por use_case
│   ├── escrituras_config.yaml  # Config de cada tipo: template, campos, conversacional
│   ├── entity_patterns.yaml    # Regex para clasificar entidades
│   └── prompts/                # Prompts externalizados (.txt)
│       ├── intent_classifier_system.txt
│       ├── intent_classifier_user.txt
│       ├── metadata_extract_system.txt
│       ├── metadata_extract_user.txt
│       ├── metadata_classify_system.txt
│       ├── metadata_classify_user.txt
│       ├── rag_system.txt
│       ├── legal_qa_system.txt
│       ├── sql_generator_system.txt
│       ├── sql_generator_user.txt
│       ├── response_generator_system.txt
│       └── response_generator_user.txt
│
├── backend/                    # FastAPI — se importa src/ directamente
│   ├── main.py                 # App FastAPI, lifespan con asyncpg pool, CORS
│   ├── dependencies.py         # get_db() injectable
│   ├── conversation_state.py   # In-memory session store para gen_state
│   ├── routers/
│   │   ├── chat.py             # POST /chat, GET /conversations, GET /conversations/:id
│   │   ├── generate.py         # GET /generate/docx/:conversation_id
│   │   ├── documents.py        # GET /documents, GET /documents/:id
│   │   └── ingest.py           # POST /ingest, GET /ingest/status/:job_id
│   ├── middleware/
│   │   ├── auth.py             # require_auth(), require_role()
│   │   └── audit.py            # write_audit_log()
│   └── models/
│       ├── requests.py         # ChatRequest, etc.
│       └── responses.py        # ChatResponse, ConversationListResponse, etc.
│
├── frontend/                   # Next.js 15 (App Router)
│   ├── app/
│   │   ├── layout.tsx          # Layout global (Lora + DM Sans)
│   │   ├── page.tsx            # Chat principal — carga historial por URL param
│   │   └── ingest/page.tsx     # Upload drag&drop + polling de status
│   ├── components/
│   │   ├── sidebar.tsx         # Lista de conversaciones, new chat
│   │   ├── chat-input.tsx      # Input con attach + send
│   │   └── message-bubble.tsx  # Badges SQL/RAG/GEN/LEX, stat cards, chips
│   └── lib/
│       ├── api.ts              # sendMessage(), uploadFile(), getConversation(), etc.
│       ├── types.ts            # SourceType, ChatMessage, ConversationDetail, etc.
│       └── source-type.ts      # Mapeo source_type → color de badge
│
├── supabase/
│   ├── schema.sql                       # Schema Postgres completo (tablas, índices, triggers)
│   ├── migration_001_add_user_id.sql    # Agrega user_id a metadata y embeddings (idempotente)
│   └── migration_002_add_legal_embeddings.sql  # Agrega tabla legal_embeddings (idempotente)
│
├── tests/
│   ├── test_router_logic.py    # Tests de routing ask_unified()
│   ├── test_gen_flow.py        # Tests de generador conversacional end-to-end
│   ├── test_generator_utils.py # Tests de DictWrapper, ValueAccessible
│   ├── test_parity.py          # Smoke tests pgvector (SQL + RAG) — requiere DATABASE_URL
│   ├── test_rag_helpers.py     # entity extraction, verify_entities
│   ├── test_database.py        # SQLite + Postgres layers
│   ├── test_sql_safety.py      # Prevención de SQL injection
│   └── test_edge_cases.py      # 135 edge cases (SQL injection, router, generadores)
│
├── scripts/
│   ├── check_secrets.py        # Detecta API keys en código (pre-commit + hook)
│   ├── validate_config.py      # Valida YAML + config_loader sin errores
│   ├── hooks/
│   │   ├── run_tests_hook.py
│   │   └── validate_yaml_hook.py
│   └── experiments/            # Scripts de benchmarks (no son infraestructura)
│       ├── run_benchmark.py
│       ├── benchmark_chunk_800.py
│       ├── benchmark_e5_chunksize.py
│       ├── benchmark_e5_instruct.py
│       ├── benchmark_embeddings.py
│       └── eval_qualitativa.py
│
├── docs/
│   └── benchmarks/             # Resultados de benchmarks de embeddings
│
├── skills/                     # Documentación interna para Claude Code
│   ├── fastapi-endpoint.md
│   ├── postgres-pgvector.md
│   ├── notarial-domain.md
│   └── testing.md
│
├── data/
│   ├── escrituras/             # PDFs originales (SRC_DIR)
│   ├── artifacts/              # Markdowns + metadata.jsonl (ARTIFACTS_DIR)
│   ├── rag_index/              # embeddings_meta.json + SHA1s (el índice vive en pgvector)
│   ├── rag_index_openai/       # Índice de referencia — OpenAI 1536d (benchmark)
│   ├── rag_index_e5_instruct/  # Índice de producción — e5-instruct 1024d (benchmark)
│   ├── legal_index/            # embeddings_meta.json + SHA1s para normativa (el índice vive en pgvector)
│   └── legal_docs/             # Fuente markdown para legal_index (CCC, leyes notariales)
│
├── docker-compose.yml          # db + backend + frontend
├── backend/Dockerfile          # Multi-stage con LibreOffice
├── frontend/Dockerfile         # Multi-stage Next.js standalone
├── .env.example                # Todas las vars con comentarios
├── .pre-commit-config.yaml
└── cli.py                      # CLI: ingest, ask, rag-build, legal-build, etc.
```

---

## Variables de entorno clave

| Variable | Descripción | Default |
|---|---|---|
| `OPENAI_API_KEY` | **Requerida** | — |
| `DATABASE_URL` | Postgres (Supabase). Si ausente, usa SQLite. | — |
| `DATABASE_PATH` | Path SQLite (fallback sin DATABASE_URL) | `data/notary.db` |
| `LLM_BACKEND` | `openai` \| `local` \| `hybrid` | `openai` |
| `LOCAL_MODEL` | Modelo Ollama para RAG synthesis y docs | `qwen3:14b` |
| `LOCAL_BASE_URL` | URL servidor Ollama | `http://localhost:11434/v1` |
| `LOCAL_API_KEY` | Placeholder para Ollama | `ollama` |
| `OLLAMA_CONTEXT_LENGTH` | Contexto Ollama (default 4096 es insuficiente) | `8192` |
| `EMBEDDINGS_BACKEND` | `openai` \| `local` | `openai` |
| `EMBEDDINGS_MODEL_LOCAL` | Modelo Ollama para embeddings locales | `qllama/multilingual-e5-large-instruct` |

> ⚠️ **Incompatibilidad de dimensiones con pgvector:** e5-large-instruct produce 1024d, pero la tabla `embeddings` tiene `vector(1536)`. `EMBEDDINGS_BACKEND=local` en producción requiere recrear el schema con `vector(1024)`. Por ahora usar siempre `EMBEDDINGS_BACKEND=openai` en producción.

| `CLERK_SECRET_KEY` | Auth JWT. Si ausente, dev-mode (`user_id="dev-user"`) | — |
| `SOFFICE_EXE` | Path a LibreOffice | `/usr/bin/soffice` |
| `NEXT_PUBLIC_API_URL` | URL del backend desde el browser | `http://localhost:8000` |
| `CORS_ORIGINS` | Origins permitidos en backend | `http://localhost:3000` |
| `SRC_DIR` | Directorio con PDFs/DOCs originales | `data/escrituras` |
| `ARTIFACTS_DIR` | Directorio de markdowns + metadata.jsonl | `data/artifacts` |
| `INDEX_DIR` | Directorio del índice RAG (meta local) | `data/rag_index` |
| `METADATA_JSONL` | Path al JSONL de metadata | `data/artifacts/metadata.jsonl` |

---

## Dominio notarial — contexto crítico

Las **escrituras públicas** son documentos legales argentinos con estructura fija:
**comparecientes** (personas que firman), **inmueble** (si aplica), **acto notarial**
(tipo de operación), **notario autorizante**, fecha y lugar.

### Taxonomía (config/casos.yaml) — tres niveles

```
acto_clase
└── acto_subclase
    └── acto_caso (leaf — identificador único usado en todo el sistema)
```

Ejemplo: `instrumento_publico_notarial` → `escritura_publica` → `compraventa_inmueble`

Hay 60+ acto_caso definidos. Antes de asumir que uno no existe, revisar `config/casos.yaml`.

### Modos del router (src/core/intent_classifier.py → LLMRoute.mode)

| Modo | Cuándo | Handler |
|---|---|---|
| `sql` | Conteos, filtros, estadísticas, búsquedas por campo | `TextToSQLEngine` / `TextToSQLEnginePg` |
| `qa` | Contenido semántico, cláusulas, facultades, detalles de escrituras | RAG (pgvector embeddings + LLM) |
| `legal_qa` | Consultas de derecho notarial argentino, normativa, requisitos formales | RAG (pgvector legal_embeddings + LLM) |
| `generate` | Pedido de generar un documento | `BaseConversationalManager` (campo a campo) |
| `chat` | Saludo, capacidades, preguntas generales | Respuestas predefinidas + gpt-4o-mini fallback |

El router nunca asume que el usuario sabe en qué modo está. La UI lo muestra con un badge de color.

### Schema de Postgres (supabase/schema.sql)

Tablas principales:
- `metadata` — un registro por escritura (file_id, **user_id**, acto_caso, fecha_iso, notario, sha1, ...)
- `comparecientes` — N por escritura (nombre, dni, tipo_entidad, representa_a, ...) — **sin user_id aún**
- `inmuebles` — N por escritura (nomenclatura_catastral, partida, valuacion_fiscal, ...) — **sin user_id aún**
- `embeddings` — chunks vectoriales por escritura (vector(1536), HNSW cosine, con **user_id**)
- `legal_embeddings` — chunks de normativa argentina — CCC, Ley 404, Ley 17.801 (**compartido entre tenants, sin user_id**)
- `conversations` + `messages` — historial de chat con gen_state JSONB
- `ingest_jobs` — estado de jobs de ingesta (queued → processing → done | error)
- `audit_log` — log de acceso (user_id, query, source_type, document_ids[])

### Multi-tenancy — estado actual

- `metadata` y `embeddings`: tienen `user_id` ✅ — todas las queries filtran por `user_id`
- `comparecientes` e `inmuebles`: **sin** `user_id` ❌ — pendiente de migración
- `legal_embeddings`: sin `user_id` por diseño (textos públicos compartidos entre tenants) ✅
- Migración disponible: `supabase/migration_001_add_user_id.sql` (para bases existentes)

---

## Sistema de generación de escrituras (data-driven)

Para agregar un nuevo tipo de escritura:
1. Agregar entrada en `config/casos.yaml` bajo el acto_caso correspondiente
2. Agregar config en `config/escrituras_config.yaml` (template_file, campos_requeridos, conversacional)
3. Crear template Jinja2 en `src/generators/templates/<nombre>.j2`
4. **No tocar código Python.** `UniversalGenerator` lo detecta automáticamente.

El generador recolecta datos campo por campo via conversación. El estado se persiste en
`conversations.gen_state` (JSONB) para sobrevivir reinicios del worker.

---

## Cómo trabajar en este proyecto

### Antes de implementar cualquier feature

1. Leer el skill relevante en `skills/`
2. Verificar que `python scripts/validate_config.py` pasa sin errores
3. Si el cambio toca `src/core/router.py` o `src/analytics/`: correr tests primero

### Tests

```bash
# Suite completa (304 tests, sin dependencias externas)
pytest tests/ -x -q

# Solo router
pytest tests/test_router_logic.py -x -q

# Solo generador
pytest tests/test_gen_flow.py -x -q

# Tests de paridad pgvector (requieren DATABASE_URL + OPENAI_API_KEY)
DATABASE_URL=postgresql://... python -m pytest tests/test_parity.py -v
```

### Servidores de desarrollo

```bash
# Backend (FastAPI)
uvicorn backend.main:app --reload --port 8000

# Frontend (Next.js)
cd frontend && npm run dev   # puerto 3000
```

### Validar antes de commitear

```bash
python scripts/check_secrets.py      # detecta API keys
python scripts/validate_config.py    # valida YAML + config_loader
pytest tests/ -x -q                  # corre tests
```

### CLI para pruebas rápidas

```bash
# Consultas
python cli.py ask "cuántas escrituras hay"          # modo SQL
python cli.py ask "qué facultades tiene este poder" # modo RAG
python cli.py ask "qué requisitos tiene una escritura pública" # modo legal_qa

# Ingesta y construcción de índices
python cli.py ingest data/escrituras/               # ingestar PDFs
python cli.py rag-build --embeddings openai         # construir índice RAG
python cli.py legal-build --embeddings openai       # indexar normativa

# Debug RAG
python cli.py rag-search "apoderado" --file-id 20-0287
python cli.py rag-ask "qué facultades tiene el poder" --file-id 20-0287
```

---

## Endpoints del backend

| Método | Path | Descripción |
|---|---|---|
| GET | `/health` | Health check (sin auth) |
| POST | `/chat` | Envía mensaje → routing inteligente |
| GET | `/conversations` | Lista conversaciones (keyset pagination por UUID) |
| GET | `/conversations/:id` | Todos los mensajes de una conversación |
| GET | `/generate/docx/:conversation_id` | Descarga DOCX generado |
| GET | `/documents` | Lista escrituras con filtros |
| GET | `/documents/:id` | Metadata + comparecientes + inmuebles |
| POST | `/ingest` | Upload PDF/DOC → retorna job_id |
| GET | `/ingest/status/:job_id` | Estado del job de ingesta |

---

## Estado del proyecto — qué está hecho y qué falta

### Hecho (mayo 2026)
- Núcleo Python completo: ingesta, RAG, text-to-SQL, generador conversacional
- Backend FastAPI con auth Clerk, audit log, paginación keyset
- Frontend Next.js con chat, sidebar, historial, ingestión drag&drop, badges SQL/RAG/GEN/LEX
- Schema Postgres + pgvector en Supabase
- Auto-selección SQLite vs Postgres según `DATABASE_URL`
- Dockerfiles y docker-compose
- Suite de 304 tests (router, generador, RAG, SQL safety, smoke tests pgvector)
- Scripts de validación y detección de secretos
- **Consolidación pgvector**: ChromaDB eliminado; RAG de escrituras y normativa en pgvector
- **Agente escribano** (`legal_qa`): RAG sobre CCC, Ley 404 CABA, Ley 17.801 y más
- **Cliente LLM centralizado** (`src/core/llm_client.py`): OpenAI + Ollama con routing por use-case via `LLM_BACKEND`
- **Pipeline de ingesta** (`src/ingest/pipeline.py`): extracción, metadata LLM, JSONL, Postgres en un módulo
- **Multi-tenancy parcial**: `user_id` en `metadata` y `embeddings`; `migration_001_add_user_id.sql` disponible

### Pendiente — corto plazo
- Deploy en producción (Railway/Fly.io para backend, Vercel para frontend)
- Conectar `DATABASE_URL` real de Supabase en entorno de producción
- Multi-tenancy completo: `comparecientes` e `inmuebles` aún sin `user_id`

### Pendiente — mediano plazo (tesis + SaaS)
- Dataset de evaluación formal (`tests/evaluation/queries.json`, 60+ queries etiquetadas)
- WebSocket o SSE para streaming de respuestas largas
- Documentación de arquitectura para la tesis (`docs/architecture.md`)
- Onboarding de escribanías reales (carga inicial de corpus, calibración de embeddings)

### Roadmap — privacidad total de datos (post-tesis)

El objetivo es poder operar **100% on-premise** sin enviar datos de clientes a OpenAI. La arquitectura (`llm_client.py`) ya soporta el switch; solo requiere:

| Componente | Hoy (prod) | Futuro (privacidad total) |
|---|---|---|
| LLM inferencia | OpenAI gpt-4o-mini | Ollama qwen3:14b (local) |
| Embeddings | OpenAI text-embedding-3-small (1536d) | e5-large-instruct via Ollama (1024d) |
| Cambio requerido en código | — | Solo env vars |
| Cambio requerido en schema | — | `vector(1536)` → `vector(1024)` + re-indexar |

El benchmark (`docs/benchmarks/`) confirmó que `multilingual-e5-large-instruct` iguala la calidad de OpenAI en el dominio notarial argentino. La transición es técnicamente viable en un sprint cuando sea prioritario.

---

## Estilo de trabajo con Claude Code

- Antes de hacer cambios grandes: explicar comportamiento actual → identificar el gap → proponer el cambio mínimo → implementar en pasos revisables
- Preferir cambios incrementales y testeables
- No tocar archivos no relacionados con la tarea
- No agregar features, abstracciones ni manejo de errores que no se pidieron
- Si algo requiere un cambio estructural, detenerse y explicar las opciones antes de implementar
