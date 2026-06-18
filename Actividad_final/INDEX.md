# Índice del showcase — NotarIA

Trabajo Final del curso "Introducción a la Ingeniería de Software Asistida por IA" (FIUBA).

---

## Estructura

| Carpeta / Archivo | Contenido |
|---|---|
| [`README.md`](README.md) | Presentación del proyecto: problema, solución, stack, estado actual |
| [`superpowers/`](superpowers/) | Flujo Brainstorming → Spec → Plan aplicado al agente escribano |
| [`claude-code-setup/`](claude-code-setup/) | Configuración de Claude Code: CLAUDE.md, settings.json, 6 skills |
| [`arquitectura/`](arquitectura/) | Diagramas Mermaid del flujo de consulta y flujo de ingesta |
| [`api/`](api/) | OpenAPI spec completo + documentación de prompts de la API |
| [`testing/`](testing/) | 4 archivos de test representativos + explicación de la convención |
| [`demo-aislada/`](demo-aislada/) | Script standalone que corre sin dependencias (`python3 sql_safety_demo.py`) |

---

## Detalle por sección

### `superpowers/`
- `specs/2026-04-05-legal-qa-agente-escribano.md` — problema, decisiones de diseño (por qué
  un índice separado sin `user_id`, por qué pgvector y no keywords, qué normativa indexar),
  schema SQL, criterios de éxito, riesgos asumidos
- `plans/2026-04-05-legal-qa-agente-escribano.md` — 10 tasks de implementación con archivos
  exactos, código esperado, y comandos de verificación para cada tarea
- `README.md` — qué es el flujo y por qué se aplicó a esta feature específica

### `claude-code-setup/`
- `CLAUDE.md` — contexto del dominio: stack, arquitectura, reglas, dominio notarial, cómo trabajar
- `settings.json` — permisos (allow/ask/deny) y variables de entorno fijadas para cada sesión
- `skills/` — 6 guías especializadas: endpoint FastAPI, Postgres/pgvector, dominio notarial,
  testing, agregar tipo de escritura, iterar sobre prompts
- `README.md` — qué rol cumple cada tipo de archivo y cómo se relacionan entre sí

### `arquitectura/`
- `architecture.md` — diagramas Mermaid del sistema: flujo de consulta (5 modos de routing),
  flujo de ingesta (PDF → markdown → metadata → pgvector), stack tecnológico, decisiones de
  diseño clave (por qué `gen_state` en JSONB, por qué auto-selección SQLite/Postgres, etc.)

### `api/`
- `openapi.yaml` — spec completo de los 9 endpoints del backend
- `openapi-prompts.md` — documentación de los prompts del sistema y sus parámetros

### `testing/`
- `test_router_logic.py` — tests del router principal con mocks (patrón central de la suite)
- `test_sql_safety.py` — tests del validador SQL (lógica pura, sin mocks necesarios)
- `test_gen_flow.py` — tests del flujo conversacional con AsyncMock del pool de DB
- `test_edge_cases.py` — 135 edge cases con `@pytest.mark.parametrize`
- `README.md` — por qué se mockea el LLM, cómo correr los tests, diferencia CI vs. evaluación de tesis

### `demo-aislada/`
- `sql_safety_demo.py` — 11 casos de validación SQL (4 queries legítimas + 7 inyecciones)
  que muestran cómo el sistema protege la DB de queries destructivas generadas por el LLM.
  Cero dependencias, corre con `python3 sql_safety_demo.py`.
- `README.md` — qué muestra, por qué se eligió esta pieza, qué ilustra del diseño

---

## Para ver el proyecto completo

El código fuente está en el repositorio `notary-ingest/` (carpeta hermana de esta).
Este showcase no incluye `src/`, `backend/`, ni `frontend/` — solo la documentación,
configuración, y evidencia de proceso.
