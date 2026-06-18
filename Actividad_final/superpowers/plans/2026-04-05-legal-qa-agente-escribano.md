# Plan: Agente Escribano — Implementación

**Spec:** `docs/superpowers/specs/2026-04-05-legal-qa-agente-escribano.md`
**Fecha:** 2026-04-05

---

## Tasks

### Task 1: Schema — tabla `legal_embeddings` y migración

**Archivo a crear:** `supabase/migration_002_add_legal_embeddings.sql`

```sql
CREATE TABLE IF NOT EXISTS legal_embeddings (
    id          SERIAL PRIMARY KEY,
    source      TEXT NOT NULL,
    chunk_ix    INTEGER NOT NULL,
    content     TEXT NOT NULL,
    vector      vector(1536) NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (source, chunk_ix)
);

CREATE INDEX IF NOT EXISTS idx_legal_embeddings_source ON legal_embeddings(source);

CREATE INDEX IF NOT EXISTS idx_legal_embeddings_vector
    ON legal_embeddings
    USING hnsw (vector vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
```

Sin columna `user_id` por diseño (ver spec).

**Comando de verificación:**
```bash
# Aplicar contra Supabase
psql $DATABASE_URL -f supabase/migration_002_add_legal_embeddings.sql

# Verificar que la tabla existe y tiene el índice HNSW
psql $DATABASE_URL -c "\d legal_embeddings"
```

---

### Task 2: Corpus de normativa — documentos fuente en `data/legal_docs/`

**Archivos a crear:** 8 archivos `.md` en `data/legal_docs/`

| Archivo | Contenido |
|---|---|
| `ccc_instrumentos_publicos.md` | Arts. 299-312 CCC |
| `ccc_mandato_poderes.md` | Arts. 362-381 CCC |
| `ccc_compraventa.md` | Arts. 1123-1171 CCC |
| `ccc_derechos_reales.md` | Arts. 1882-2276 CCC (selección) |
| `ccc_donacion.md` | Arts. 1542-1573 CCC |
| `ccc_contratos_forma.md` | Arts. 1015-1020 CCC |
| `ley_404_caba.md` | Ley Notarial 404 de CABA + Dec. Reg. 1624/00 |
| `ley_17801_registro_propiedad.md` | Ley 17.801 — arts. relevantes al ejercicio notarial |

**Criterio de selección de artículos:** incluir solo los que un escribano consultaría en su
práctica diaria; no transcribir la ley completa. Los artículos sobre procedimiento judicial
o normas que no tocan al escribano quedan fuera.

**No versionar en el repositorio público** si los textos tienen restricciones de copyright.
Para el MVP usamos transcripción de los artículos relevantes (texto oficial, dominio público).

---

### Task 3: Indexador de normativa — `build_legal_index()` en `src/rag/indexer_pg.py`

**Archivo a modificar:** `src/rag/indexer_pg.py` — agregar función `build_legal_index()`.

La función reutiliza exactamente los mismos helpers que `build_index()`:
- `_get_embedder()` de `src/rag/indexer.py` — mismo embedder, misma dimensión
- `_chunk_markdown()` de `src/rag/indexer.py` — mismo chunker semántico
- `sha1_file()` de `src/ingest/utils.py` — para skip de archivos sin cambios

Diferencia clave respecto a `build_index()`:
- Escribe en `legal_embeddings`, no en `embeddings`
- No recibe `user_id` — no lo pasa al INSERT
- Usa `legal_sha1s.json` en `index_dir` para no pisar el `file_sha1s_pg.json` de escrituras

**Verificación:**
```bash
DATABASE_URL=... OPENAI_API_KEY=... python cli.py legal-build --embeddings openai
# Salida esperada: {"chunks": N, "files": 8, "skipped": 0}

# Verificar que los chunks llegaron a Postgres
psql $DATABASE_URL -c "SELECT source, COUNT(*) FROM legal_embeddings GROUP BY source ORDER BY source;"
```

---

### Task 4: Función de búsqueda — `search_legal_pg()` en `src/rag/indexer_pg.py`

**Archivo a modificar:** `src/rag/indexer_pg.py` — agregar función `search_legal_pg()`.

```python
async def search_legal_pg(
    query_vector: List[float],
    k: int = 8,
    dsn: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Búsqueda vectorial en legal_embeddings. Sin filtro user_id — normativa compartida.
    Mismo formato de retorno que search_similar_pg() para compatibilidad con router.py.
    """
    _dsn = dsn or os.environ.get("DATABASE_URL")
    ...
    sql = """
        SELECT source, chunk_ix, content,
               1 - (vector <=> CAST($1 AS vector)) AS score
        FROM legal_embeddings
        ORDER BY vector <=> CAST($1 AS vector)
        LIMIT $2
    """
```

El formato de retorno debe coincidir con `search_similar_pg()`:
```python
{"document": content, "metadata": {"source": source, "chunk_ix": chunk_ix}, "score": float}
```

---

### Task 5: API de búsqueda pública — `query_legal_index()` en `src/rag/search.py`

**Archivo a modificar:** `src/rag/search.py` — agregar función `query_legal_index()`.

```python
def query_legal_index(query: str, k: int = 8, index_dir=None) -> List[Dict]:
    from src.rag.indexer_pg import search_legal_pg
    embed = _get_query_embedder()
    q_vec = embed([query])[0]
    return run_sync(search_legal_pg(query_vector=q_vec, k=k))
```

`index_dir` se mantiene como parámetro para compatibilidad con el CLI pero se ignora.

No implementar `verify_entities` para legal: los textos normativos no tienen entidades
nombradas en el sentido de la función `extract_named_entities()` (no hay nombres propios,
DNIs, razones sociales). El filtrado por entidades no aporta nada y añade latencia.

---

### Task 6: System prompt del agente escribano

**Archivo a crear:** `config/prompts/legal_qa_system.txt`

El prompt debe definir:
1. Rol: "asistente jurídico especializado en derecho notarial argentino, foco CABA"
2. Base normativa que conoce (listar las leyes del corpus)
3. Cómo citar: artículo específico entre paréntesis, ej. "(art. 1017 CCC)"
4. Qué distinguir: regla general vs. excepción vs. práctica habitual en CABA
5. Qué no hacer: no inventar artículos, no asesoramiento impositivo, no derecho provincial
6. Cuándo derivar: casos concretos con matices → recomendar consulta con escribano

**Verificar** con tres queries manuales representativas antes de integrar al router:
```bash
python cli.py ask "cuáles son los requisitos de una escritura pública"
python cli.py ask "qué diferencia hay entre poder general y especial"
python cli.py ask "qué es el tracto sucesivo"
```

---

### Task 7: Integración en el router — `_answer_from_legal_qa()` en `src/core/router.py`

**Archivo a modificar:** `src/core/router.py`

Agregar la función `_answer_from_legal_qa()` y conectarla en `ask_unified()`:

```python
def _answer_from_legal_qa(question: str, k: int = 8) -> AskResponse:
    system = load_prompt("legal_qa_system")
    try:
        hits = query_legal_index(question, k=k)
    except Exception:
        hits = []   # degradación con gracia: sin RAG, responde igual

    if hits:
        context = "\n\n---\n\n".join(
            f"[{h['metadata'].get('source', '')}]\n{h['document']}" for h in hits
        )
        prompt = f"Consulta: {question}\n\nFuentes jurídicas:\n{context}\n\nRespondé en español jurídico argentino."
    else:
        prompt = f"Consulta: {question}\n\nRespondé en español jurídico argentino."

    ans = llm_answer_with_context(system, prompt, temperature=0.0)
    return AskResponse(
        answer=ans or "No pude responder esta consulta...",
        source_type="legal",
        extra={"hits": hits},
    )
```

En `ask_unified()`, agregar antes del bloque SQL:
```python
if mode == "legal_qa":
    return _answer_from_legal_qa(question)
```

---

### Task 8: Actualizar intent classifier — prompt con ejemplos de `legal_qa`

**Archivo a modificar:** `config/prompts/intent_classifier_system.txt`

Agregar la descripción del modo `legal_qa` con ejemplos que lo distingan de `qa` y `sql`:

```
- legal_qa: Para consultas jurídicas o notariales GENERALES, no sobre escrituras específicas del sistema
  IMPORTANTE: Usá legal_qa cuando la pregunta es sobre el DERECHO o la PRÁCTICA NOTARIAL en general.
  Ejemplos legal_qa: "cuáles son los requisitos para una compraventa", "qué es un poder especial",
                     "qué dice el artículo 299 del CCC", "diferencia entre poder general y especial",
                     "qué es el tracto sucesivo", "cómo funciona la inhibición general"
```

La distinción crítica que debe quedar clara para el LLM:
- "qué requisitos tiene una escritura pública" → `legal_qa` (pregunta sobre el derecho)
- "cuántas escrituras hay" → `sql` (pregunta sobre el corpus)
- "qué dice la escritura 20-0287 sobre el precio" → `qa` (pregunta sobre contenido específico)

---

### Task 9: Badge LEX en el frontend — `src/frontend/`

**Archivos a modificar:**
- `frontend/lib/source-type.ts` — agregar mapeo `"legal"` → color violeta + label "LEX"
- `frontend/components/message-bubble.tsx` — el badge ya se renderiza genéricamente desde `source_type`; verificar que `"legal"` produce el badge correcto

```typescript
// source-type.ts
export const SOURCE_TYPE_CONFIG = {
  sql: { label: "SQL", color: "bg-blue-100 text-blue-800" },
  rag: { label: "RAG", color: "bg-green-100 text-green-800" },
  generate: { label: "GEN", color: "bg-orange-100 text-orange-800" },
  legal: { label: "LEX", color: "bg-violet-100 text-violet-800" },
  chat: { label: "CHAT", color: "bg-gray-100 text-gray-600" },
}
```

**Verificación:** abrir el frontend, enviar "qué es el tracto sucesivo", confirmar que la
respuesta muestra badge "LEX" violeta.

---

### Task 10: Tests

**Archivo a crear:** `tests/test_legal_qa.py`

**Casos a cubrir:**

```python
# 1. Clasificación correcta en el router (mock LLM)
def test_router_routes_legal_qa():
    with patch("src.core.intent_classifier.classify_intent_llm") as mock_clf:
        mock_clf.return_value = {"mode": "legal_qa", "confidence": 0.95}
        with patch("src.core.router.query_legal_index") as mock_search:
            mock_search.return_value = []
            with patch("src.core.router.llm_answer_with_context") as mock_llm:
                mock_llm.return_value = "El art. 1017 CCC..."
                resp = ask_unified("qué requisitos tiene una escritura pública")
    assert resp.source_type == "legal"

# 2. Degradación con gracia: legal_qa funciona sin DATABASE_URL
def test_legal_qa_degrades_without_db():
    with patch("src.rag.indexer_pg.search_legal_pg") as mock_pg:
        mock_pg.side_effect = RuntimeError("DATABASE_URL no configurado")
        with patch("src.core.router.llm_answer_with_context") as mock_llm:
            mock_llm.return_value = "Respuesta sin RAG"
            resp = _answer_from_legal_qa("qué es un poder especial")
    assert resp.answer == "Respuesta sin RAG"
    assert resp.extra["hits"] == []

# 3. La búsqueda NO filtra por user_id (verificar firma de search_legal_pg)
def test_search_legal_pg_has_no_user_id_param():
    import inspect
    from src.rag.indexer_pg import search_legal_pg
    sig = inspect.signature(search_legal_pg)
    assert "user_id" not in sig.parameters

# 4. Formato de retorno compatible con router (mismo que search_similar_pg)
def test_search_legal_pg_return_format():
    with patch("asyncpg.create_pool") as mock_pool:
        # mock setup...
        hits = [{"document": "texto", "metadata": {"source": "ccc_mandato_poderes"}, "score": 0.87}]
        for hit in hits:
            assert "document" in hit
            assert "metadata" in hit
            assert "score" in hit
```

**Restricción:** ningún test llama a OpenAI ni a Postgres real. Todo mockeado.

**Comando:**
```bash
pytest tests/test_legal_qa.py -x -q
```
