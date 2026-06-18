# Skill: Postgres + pgvector

Lee este archivo completo antes de crear tablas, queries, o migraciones.

## Setup inicial en Supabase

Habilitar la extensión pgvector ejecutando en el SQL editor de Supabase:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

La dimensión de los embeddings es 1536 (OpenAI text-embedding-3-small).
No cambiar esta dimensión sin migrar todos los embeddings existentes.

## Schema completo

```sql
-- Documentos indexados
CREATE TABLE metadata (
    file_id         TEXT PRIMARY KEY,
    acto_clase      TEXT,
    acto_subclase   TEXT,
    acto_caso       TEXT,
    lugar           TEXT,
    fecha_iso       DATE,
    anio            INTEGER,
    notario         TEXT,
    raw_json        JSONB,
    sha1            TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Personas que comparecen en escrituras
CREATE TABLE comparecientes (
    id                          SERIAL PRIMARY KEY,
    file_id                     TEXT NOT NULL REFERENCES metadata(file_id) ON DELETE CASCADE,
    nombre                      TEXT,
    dni                         TEXT,
    cuil_cuit                   TEXT,
    domicilio                   TEXT,
    representa_a                TEXT,
    tipo_entidad                TEXT,
    tipo_entidad_representada   TEXT
);

-- Inmuebles referenciados en escrituras
CREATE TABLE inmuebles (
    id                      SERIAL PRIMARY KEY,
    file_id                 TEXT NOT NULL REFERENCES metadata(file_id) ON DELETE CASCADE,
    descripcion             TEXT,
    nomenclatura_catastral  TEXT,
    partida                 TEXT,
    matricula               TEXT,
    valuacion_fiscal        TEXT,
    vir_vr                  TEXT
);

-- Chunks de texto con embeddings vectoriales
CREATE TABLE embeddings (
    id              SERIAL PRIMARY KEY,
    file_id         TEXT NOT NULL REFERENCES metadata(file_id) ON DELETE CASCADE,
    chunk_ix        INTEGER NOT NULL,
    section_type    TEXT,
    content         TEXT NOT NULL,
    vector          vector(1536) NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Conversaciones del chat
CREATE TABLE conversations (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     TEXT NOT NULL,
    title       TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Mensajes dentro de conversaciones
CREATE TABLE messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content         TEXT NOT NULL,
    source_type     TEXT CHECK (source_type IN ('sql', 'rag', 'generate')),
    extra           JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Estado de jobs de ingesta
CREATE TABLE ingest_jobs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     TEXT NOT NULL,
    file_name   TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'queued'
                    CHECK (status IN ('queued', 'processing', 'done', 'error')),
    error_msg   TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Log de auditoría
CREATE TABLE audit_log (
    id                  SERIAL PRIMARY KEY,
    user_id             TEXT NOT NULL,
    endpoint            TEXT NOT NULL,
    query               TEXT,
    source_type         TEXT,
    document_ids        TEXT[],
    timestamp           TIMESTAMPTZ DEFAULT NOW()
);
```

## Índices requeridos

```sql
CREATE INDEX idx_metadata_acto_caso ON metadata(acto_caso);
CREATE INDEX idx_metadata_anio ON metadata(anio);
CREATE INDEX idx_metadata_notario ON metadata(notario);
CREATE INDEX idx_comparecientes_file_id ON comparecientes(file_id);
CREATE INDEX idx_comparecientes_nombre ON comparecientes(nombre);
CREATE INDEX idx_comparecientes_dni ON comparecientes(dni);
CREATE INDEX idx_inmuebles_file_id ON inmuebles(file_id);
CREATE INDEX idx_embeddings_file_id ON embeddings(file_id);
CREATE INDEX idx_conversations_user_id ON conversations(user_id);
CREATE INDEX idx_messages_conversation_id ON messages(conversation_id);
CREATE INDEX idx_audit_log_user_id ON audit_log(user_id);

-- Índice vectorial HNSW para búsqueda semántica eficiente
CREATE INDEX idx_embeddings_vector ON embeddings
    USING hnsw (vector vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
```

## Búsqueda vectorial

```python
# Buscar los k chunks más similares a un embedding de query
async def search_similar(conn, query_vector: list[float], k: int = 6,
                         file_id: str = None) -> list[dict]:
    where = "WHERE file_id = $2" if file_id else ""
    params = [query_vector, file_id, k] if file_id else [query_vector, k]
    k_param = "$3" if file_id else "$2"

    rows = await conn.fetch(f"""
        SELECT
            e.file_id,
            e.chunk_ix,
            e.section_type,
            e.content,
            1 - (e.vector <=> $1::vector) AS score
        FROM embeddings e
        {where}
        ORDER BY e.vector <=> $1::vector
        LIMIT {k_param}
    """, *params)
    return [dict(r) for r in rows]
```

## Query híbrida (metadata + vectorial)

```python
# Buscar chunks semánticos solo en escrituras que cumplen un filtro SQL
async def hybrid_search(conn, query_vector: list[float],
                        acto_caso: str = None, anio: int = None,
                        k: int = 6) -> list[dict]:
    filters = []
    params = [query_vector]

    if acto_caso:
        params.append(acto_caso)
        filters.append(f"m.acto_caso = ${len(params)}")
    if anio:
        params.append(anio)
        filters.append(f"m.anio = ${len(params)}")

    where = "WHERE " + " AND ".join(filters) if filters else ""
    params.append(k)

    rows = await conn.fetch(f"""
        SELECT
            e.file_id,
            e.chunk_ix,
            e.content,
            m.acto_caso,
            m.fecha_iso,
            m.notario,
            1 - (e.vector <=> $1::vector) AS score
        FROM embeddings e
        JOIN metadata m ON e.file_id = m.file_id
        {where}
        ORDER BY e.vector <=> $1::vector
        LIMIT ${len(params)}
    """, *params)
    return [dict(r) for r in rows]
```

## Convenciones de naming

- Tablas: `snake_case`, plural (`metadata` es excepción histórica, mantener)
- Columnas: `snake_case`
- Índices: `idx_{tabla}_{columna}`
- Foreign keys: siempre con `ON DELETE CASCADE` cuando el hijo no tiene sentido
  sin el padre (comparecientes, inmuebles, embeddings → metadata)
- Timestamps: siempre `TIMESTAMPTZ` (con timezone), nunca `TIMESTAMP`
- IDs de documentos notariales: `TEXT` (formato `"20-0287"`, no UUID)
- IDs de entidades internas: `UUID` con `gen_random_uuid()`

## Conexión desde Python (asyncpg)

```python
import asyncpg
import os

async def get_db_pool():
    return await asyncpg.create_pool(
        dsn=os.getenv("DATABASE_URL"),
        min_size=2,
        max_size=10,
        command_timeout=30
    )
```

El pool se inicializa una vez al arrancar FastAPI y se inyecta como dependencia.
Nunca crear conexiones individuales por request.
