# Skill: Testing en NotarIA

Lee este archivo completo antes de escribir o modificar tests.

## Dos capas de tests con propósitos distintos

**Capa 1 — Tests de CI (rápidos, sin datos reales)**
- Ubicación: `tests/`
- Datos: corpus sintético en `tests/fixtures/escrituras_sinteticas/`
- Cuándo corren: automáticamente en cada push (hook PostToolUse + GitHub Actions)
- Objetivo: detectar regresiones en el router, extracción, y generación
- Restricción: nunca usar escrituras reales, nunca llamar a OpenAI en CI

**Capa 2 — Evaluación de tesis (con corpus real, con subagents)**
- Ubicación: `tests/evaluation/`
- Datos: las 100 escrituras reales del corpus (solo en local, nunca en repo)
- Cuándo corren: manualmente antes de hitos de la tesis
- Objetivo: medir accuracy del router, SQL, y RAG para el informe académico
- Resultado: reporte en `tests/evaluation/reports/` con métricas formales

## Correr los tests

```bash
# Tests de CI completos
python -m pytest tests/ -x -q

# Solo tests del router
python -m pytest tests/test_router.py -v

# Solo tests de analytics
python -m pytest tests/test_ask_meta.py -v

# Evaluación completa de tesis (requiere corpus real y OpenAI)
python tests/evaluation/run_evaluation.py
```

## Estructura de un test de router

El router es el componente más crítico. Cada test verifica que una pregunta
sea clasificada en el modo correcto.

```python
import pytest
from pathlib import Path
from unittest.mock import patch
from src.core.router import ask_unified

# Fixtures del corpus sintético
METADATA_JSONL = Path("tests/fixtures/metadata_sintetico.jsonl")
INDEX_DIR = Path("tests/fixtures/rag_index_sintetico")

@pytest.mark.parametrize("question,expected_mode", [
    ("cuántas escrituras hay", "sql"),
    ("escrituras de 2023", "sql"),
    ("detalle de la escritura 20-0001", "sql"),
    ("qué facultades tiene el apoderado en 20-0001", "qa"),
    ("qué dice sobre el precio", "qa"),
    ("generar poder general", "generate_escritura"),
    ("quiero hacer una compraventa", "generate_escritura"),
])
def test_router_classifies_correctly(question, expected_mode):
    response = ask_unified(
        question=question,
        metadata_jsonl=METADATA_JSONL,
        index_dir=INDEX_DIR,
    )
    assert response.source_type == expected_mode or \
           response.source_type in ["poder_generator", "tipo_detection"], \
           f"'{question}' → esperado '{expected_mode}', obtenido '{response.source_type}'"
```

## Fixtures sintéticas requeridas

El corpus sintético debe existir en `tests/fixtures/` antes de correr CI.
Contiene escrituras que reproducen la estructura real sin datos identificatorios.

```
tests/fixtures/
  escrituras_sinteticas/        # 20 archivos .md con estructura real
  metadata_sintetico.jsonl      # Metadata extraída de las escrituras sintéticas
  rag_index_sintetico/          # Índice ChromaDB o pgvector de las sintéticas
```

Para generar el corpus sintético por primera vez:
```bash
python tests/fixtures/generate_synthetic_corpus.py
```

## Evaluación de tesis con subagents

El script de evaluación lanza tres subagents en paralelo usando el tool `Task`
de Claude Code. Cada subagent corre su subset del dataset y escribe resultados
en un archivo JSON. El agente principal consolida y genera el reporte.

```
tests/evaluation/
  queries.json              # 60 queries etiquetadas (20 SQL + 20 QA + 20 ambiguas)
  run_evaluation.py         # Orquestador principal
  agents/
    eval_sql.py             # Subagent A: valida respuestas SQL
    eval_rag.py             # Subagent B: valida citas RAG
    eval_router.py          # Subagent C: valida clasificación del router
  reports/                  # Reportes generados (no versionar)
```

### Formato de queries.json

```json
[
  {
    "id": "sql_001",
    "question": "cuántas escrituras hay",
    "mode": "sql",
    "expected_answer_type": "count",
    "expected_value": 83
  },
  {
    "id": "qa_001",
    "question": "qué facultades tiene el apoderado en 20-0286",
    "mode": "qa",
    "file_id": "20-0286",
    "expected_fragments": ["administrar", "juicio", "bancarias"]
  },
  {
    "id": "amb_001",
    "question": "información sobre la escritura 20-0287",
    "mode": "sql",
    "note": "ambigua pero debe ir a SQL porque pide datos estructurados"
  }
]
```

## Criterios de aceptación para la tesis

Estos números deben aparecer en el reporte final de evaluación:

| Métrica | Mínimo aceptable | Objetivo |
|---|---|---|
| Router accuracy | 90% (18/20 queries) | 95% |
| SQL accuracy | 85% | 90% |
| RAG citation accuracy | 80% | 85% |

Si no se alcanzan, revisar `config/prompts/` antes de tocar código Python.
Los prompts son la primera palanca de mejora, el código es la última.

## Qué NO hacer en tests

- No usar las escrituras reales en tests que van a CI o GitHub Actions
- No llamar a la API de OpenAI en tests unitarios (mockear el LLM)
- No hardcodear file_ids reales como "20-0287" en tests de CI
- No commitear el directorio `tests/evaluation/reports/`
- No asumir un número fijo de escrituras en el corpus real (puede cambiar)
