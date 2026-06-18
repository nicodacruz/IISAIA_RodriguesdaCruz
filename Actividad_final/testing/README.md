# Convención de testing en NotarIA

El proyecto tiene 304 tests que corren offline — sin llamadas a OpenAI, sin Postgres, sin
ninguna variable de entorno configurada. Esta es la decisión de diseño más importante de
la suite de tests, y vale la pena explicarla.

---

## Por qué los tests mockean el LLM

Los tests de CI nunca llaman a la API de OpenAI. En su lugar, mockean el LLM y controlan
exactamente qué devuelve. Hay tres razones:

1. **Velocidad y costo** — Una suite de 304 tests que llama a la API tomaría minutos y
   costaría dinero. Con mocks corre en segundos y funciona offline.

2. **Determinismo** — Los LLMs son no-deterministas. Un test que depende de la respuesta
   real del modelo puede fallar por un cambio de temperatura, un cambio de modelo, o
   simplemente variación natural. Los tests de CI deben ser reproducibles.

3. **Separación de responsabilidades** — Los tests de CI verifican que la *lógica de routing,
   manejo de estado, y procesamiento de respuestas* funciona correctamente, dado que el LLM
   devuelve una respuesta válida. La calidad de las respuestas del LLM se evalúa por separado,
   con el corpus real, en los tests de evaluación de la tesis (que sí llaman a OpenAI).

El patrón estándar para mockear el LLM en este proyecto:

```python
os.environ.setdefault("OPENAI_API_KEY", "sk-test-notaria-fake-key-for-unit-tests")

@patch("src.core.router.classify_intent_llm", return_value={"mode": "sql", ...})
@patch("src.core.router._answer_from_metadata", return_value=AskResponse(...))
def test_sql_routing(self, mock_meta, mock_clf):
    resp = ask_unified("cuántas escrituras hay")
    mock_meta.assert_called_once()
    assert resp.source_type == "metadata"
```

La clave es que `classify_intent_llm` (el único LLM call en el router) está mockeado, y los
handlers downstream también. El test verifica el *flujo* del router, no el contenido de las
respuestas.

---

## Los cuatro archivos de test incluidos

### `test_router_logic.py`
Tests del router `ask_unified()`. Verifica que cada modo (sql, qa, generate, chat) llama
al handler correcto y preserva el `source_type`. Es el archivo más representativo de la
convención de mocking.

### `test_sql_safety.py`
Tests de `SQLGenerator.validate_sql()` y `QueryExecutor._detect_query_type()`. Estos son
tests *puramente unitarios* sin ningún mock — la función `validate_sql` es lógica Python
pura (regex + frozenset) que no necesita servicios externos. Muestra el otro extremo:
cuando el código es puro, el test es directo.

### `test_gen_flow.py`
Tests del flujo conversacional de generación de documentos (DOCX). El más complejo: mockea
un pool de base de datos asyncpg, simula turnos de conversación, y verifica que el estado
del generador (`gen_state`) se persiste correctamente. Muestra cómo testear flujos
stateful con AsyncMock.

### `test_edge_cases.py`
135 edge cases para componentes críticos: inyección SQL por comentarios, inputs vacíos,
nombres acentuados en entidades, fechas bisiesto, CUIL/CUIT malformados, y más. Muestra
el uso de `@pytest.mark.parametrize` para cubrir variantes sin repetir código.

---

## Dos capas de tests — CI vs. evaluación de tesis

**Capa 1 — Tests de CI** (`tests/` en el proyecto): los 304 tests de esta suite. Sin datos
reales, sin API calls. Corren en cada push.

**Capa 2 — Evaluación de tesis** (`tests/evaluation/` — no en este showcase): dataset de
60+ queries etiquetadas contra el corpus real. Miden accuracy del router, SQL, y RAG con
números formales (objetivo: 90% router, 85% SQL, 80% RAG citation). Corren manualmente
antes de hitos de la tesis, nunca en CI.

La separación existe porque son preguntas distintas: CI pregunta "¿rompí algo?", la
evaluación de tesis pregunta "¿qué tan bien funciona el sistema?".

---

## Cómo correr los tests (desde el proyecto `notary-ingest/`)

```bash
# Suite completa
pytest tests/ -x -q

# Solo los archivos de este showcase
pytest tests/test_router_logic.py tests/test_sql_safety.py -v

# Solo edge cases
pytest tests/test_edge_cases.py -v
```

No se necesita `DATABASE_URL` ni `OPENAI_API_KEY` reales — cualquier valor dummy sirve
(los tests setean `os.environ.setdefault("OPENAI_API_KEY", "sk-test-...")` al inicio).
