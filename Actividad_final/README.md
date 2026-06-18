# NotarIA — Showcase del Trabajo Final

**Curso:** Introducción a la Ingeniería de Software Asistida por IA — FIUBA
**Proyecto:** NotarIA — Sistema de IA para Escribanías Argentinas

---

## El problema

Las escribanías argentinas trabajan con un corpus de escrituras públicas acumulado durante
años. Cada escritura es un documento legal denso (10-30 páginas) con estructura semiestandarizada:
comparecientes, inmueble, tipo de acto, notario, fecha. Hoy ese corpus es papel o PDF: no se
puede consultar, no se puede cruzar, no se puede reusar.

Un escribano que quiere saber "cuántos poderes generales otorgamos este año" tiene que revisar
manualmente. Uno que necesita recordar las facultades exactas del poder 20-0287 tiene que abrir
el PDF y leerlo. Y uno que tiene una duda jurídica ("¿qué dice el CCC sobre la forma de la
escritura pública?") tiene que buscar en los PDFs de las leyes.

## La solución

NotarIA convierte ese corpus inerte en una base de conocimiento consultable en lenguaje natural.
El sistema hace cuatro cosas:

1. **Ingesta** — convierte PDFs/DOCs en texto estructurado y extrae metadata (acto, partes, inmueble, notario) usando un LLM
2. **Consultas SQL** — responde preguntas sobre el corpus ("¿cuántas compraventas hay de 2024?") generando SQL a partir de lenguaje natural
3. **RAG sobre escrituras** — responde preguntas semánticas sobre el contenido ("¿qué facultades tiene el apoderado en 20-0286?") usando embeddings vectoriales
4. **Agente escribano** — responde consultas jurídicas sobre normativa argentina (CCC, Ley 404, Ley 17.801) con un índice RAG separado sobre textos normativos
5. **Generador de documentos** — genera escrituras nuevas (DOCX) recolectando datos campo a campo mediante una conversación guiada

El usuario interactúa con todo esto a través de un chat unificado. El sistema clasifica cada
mensaje con un LLM y lo enruta al handler correcto. La UI muestra badges SQL / RAG / GEN / LEX
para que el usuario entienda qué tipo de respuesta recibió.

## Por qué este proyecto para el curso

NotarIA fue construido enteramente con asistencia de Claude Code, y el desarrollo del curso
coincidió con una de sus features más complejas: el **agente escribano** (`legal_qa`). Esta
feature requirió decisiones de diseño no triviales (índice compartido sin `user_id`, prompt
especializado, degradación con gracia), y el flujo Brainstorming → Spec → Plan que propone
el curso fue la metodología usada para llevarla adelante.

El proyecto también ofrece un caso concreto de cómo Claude Code se integra en un flujo real
de desarrollo: CLAUDE.md con contexto del dominio, skills por área de conocimiento,
settings.json con permisos precisos, y tests que mockean el LLM para correr en CI sin
llamadas externas.

## Stack tecnológico

| Capa | Tecnología |
|---|---|
| Frontend | Next.js 15 (App Router) + shadcn/ui |
| Backend | FastAPI + asyncpg |
| Base de datos | Supabase (Postgres + pgvector) |
| Auth | Clerk (JWT); dev-mode sin configuración |
| LLM | OpenAI gpt-4o-mini (intent, SQL, síntesis); Ollama qwen3:14b (opcional, local) |
| Embeddings | OpenAI text-embedding-3-small (1536d) |
| Búsqueda vectorial | pgvector HNSW — escrituras (k=6) y normativa (k=8) |
| Generación de documentos | Jinja2 + python-docx, data-driven desde YAML |
| Deploy | Railway (backend) + Vercel (frontend) |

## Estado del proyecto (junio 2026)

- Núcleo Python completo: ingesta, RAG, text-to-SQL, generador conversacional
- Backend FastAPI con auth, audit log, paginación keyset
- Frontend Next.js con chat, sidebar, historial, ingestión drag&drop
- 304 tests que corren offline (sin OpenAI ni Postgres)
- Schema Postgres + pgvector en Supabase

Pendiente: deploy en producción, dataset de evaluación formal para la tesis (dic 2026).

## Cómo navegar este showcase

Ver [`INDEX.md`](INDEX.md) para el índice completo de subcarpetas.
