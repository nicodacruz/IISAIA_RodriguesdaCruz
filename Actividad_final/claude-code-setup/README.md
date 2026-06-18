# Configuración de Claude Code en NotarIA

Este directorio contiene los archivos que configuran el comportamiento de Claude Code en el
proyecto. Son cuatro tipos distintos con roles complementarios.

---

## `CLAUDE.md` — El contexto del dominio

Claude Code lee `CLAUDE.md` al inicio de cada conversación y lo incorpora como contexto
persistente. Es el equivalente a la documentación de onboarding que le darías a un
desarrollador nuevo que empieza a trabajar en el proyecto.

En NotarIA, `CLAUDE.md` contiene:
- Descripción del sistema y sus prioridades de diseño
- El stack completo con su estado actual
- El flujo de una consulta y el flujo de ingesta (en ASCII)
- Reglas que nunca se rompen (ej: "no hardcodear secretos", "no cambios arquitecturales sin acordar")
- El dominio notarial: glosario, taxonomía de actos, schema de Postgres
- Cómo trabajar en el proyecto: qué correr antes de commitear, cómo usar la CLI

Sin `CLAUDE.md`, Claude Code tiene que derivar todo el contexto de los archivos en cada
conversación. Con él, el modelo ya sabe que `acto_caso` es un identificador de tres niveles
cargado desde YAML, que los tests mockean el LLM en lugar de llamarlo de verdad, y que tocar
`src/core/router.py` requiere correr los tests antes de continuar.

---

## `settings.json` — Permisos y entorno de ejecución

`settings.json` (en `.claude/settings.json` en el proyecto real) define qué comandos puede
ejecutar Claude Code sin pedir confirmación al usuario.

Los permisos están organizados en tres niveles:

```json
"allow"  → Claude ejecuta sin preguntar     (pytest, git status/diff/log/add/commit, ls, grep)
"ask"    → Claude pregunta antes de ejecutar (git push, pip install, npm install)
"deny"   → Claude nunca ejecuta             (rm -rf, cat .env, git push --force, git reset --hard)
```

La lógica es: operaciones de lectura y verificación son automáticas; operaciones que
modifican el entorno o tienen efectos externos requieren confirmación; operaciones
destructivas están bloqueadas.

El bloque `env` fija variables de entorno para todas las sesiones:
```json
"LLM_BACKEND": "openai",
"EMBEDDINGS_BACKEND": "openai",
"DATABASE_PATH": "data/notary.db"
```

Esto asegura que Claude Code siempre opera en modo OpenAI (no Ollama local) y con SQLite
como fallback, independientemente del entorno del desarrollador.

---

## `skills/` — Guías de dominio para tareas específicas

Las skills son documentos Markdown que Claude Code lee antes de encarar una tarea
específica. A diferencia de `CLAUDE.md` (que siempre se lee), una skill se carga solo
cuando la tarea es relevante.

| Archivo | Cuándo se usa |
|---|---|
| `fastapi-endpoint.md` | Crear o modificar endpoints del backend |
| `postgres-pgvector.md` | Crear tablas, queries, o migraciones en Postgres |
| `notarial-domain.md` | Cualquier código que involucre datos de escrituras o queries al corpus |
| `testing.md` | Escribir o modificar tests |
| `add-escritura-type.md` | Agregar un nuevo tipo de escritura al sistema |
| `update-prompt.md` | Iterar sobre los prompts en `config/prompts/` |

El contenido de las skills es conocimiento que no se puede derivar del código solo: por
ejemplo, que `acto_caso` nunca se hardcodea (siempre se carga desde YAML), que los tests
de CI nunca llaman a OpenAI, o que hay una deuda técnica en las templates Jinja2 donde el
nombre del campo en el config no coincide con el de la variable en la template.

---

## La relación entre los tres

```
CLAUDE.md          → "qué es este proyecto y cómo funciona globalmente"
settings.json      → "qué puede hacer Claude Code automáticamente"
skills/            → "qué tener en cuenta para esta tarea específica"
```

`CLAUDE.md` es el contexto de fondo que siempre está presente. `settings.json` es la
configuración de permisos que define el nivel de autonomía del agente. Las skills son
conocimiento especializado que se activa on-demand.

Los tres archivos existen en el repositorio y se versionan junto con el código. Cuando
la arquitectura cambia, `CLAUDE.md` se actualiza. Cuando se agrega un nuevo tipo de
escritura, `add-escritura-type.md` puede actualizarse. El agente y el proyecto evolucionan
juntos.
