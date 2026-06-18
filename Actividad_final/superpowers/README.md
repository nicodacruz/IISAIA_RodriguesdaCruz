# Flujo Superpowers: Brainstorming → Spec → Plan

Este directorio contiene los artefactos del flujo Brainstorming → Spec → Plan aplicado a
la feature del **agente escribano** (`legal_qa`), que permite a los usuarios consultar
normativa notarial argentina en lenguaje natural.

## Qué es el flujo y por qué se usó aquí

El flujo tiene tres etapas:

1. **Brainstorming** — explorar el espacio del problema sin comprometerse con ninguna solución.
   Preguntas clave: ¿cuál es el gap real? ¿qué alternativas existen? ¿cuáles son los riesgos?

2. **Spec** — tomar decisiones de diseño y documentarlas. La spec no describe implementación;
   describe *decisiones* y sus *justificaciones*. Es el documento que un revisor debe leer para
   entender por qué el sistema quedó como quedó, no solo cómo.

3. **Plan** — descomponer la spec en tareas de implementación concretas y ordenadas.
   Cada tarea tiene archivos específicos, código esperado, y comandos de verificación.

La feature del agente escribano fue elegida para este flujo porque involucró decisiones
no obvias que merecen documentación explícita:

- **¿Por qué un índice RAG separado (`legal_embeddings`) sin `user_id`?** La normativa es
  pública — mezclarla con el corpus de escrituras requeriría duplicarla por tenant.

- **¿Por qué un system prompt especializado y no el chat genérico?** Los escribanos tienen
  formación jurídica; un tono casual o respuestas ambiguas serían peores que no tener la feature.

- **¿Por qué pgvector para normativa y no búsqueda por keywords?** Las consultas de los
  usuarios no usan vocabulario técnico: "qué necesito para vender un departamento" es
  semánticamente equivalente a "requisitos para actos de disposición de inmuebles".

Estos razonamientos, si no quedan escritos en una spec, se pierden. Dos semanas después
alguien podría "simplificar" el schema agregando `user_id` a `legal_embeddings` sin entender
por qué no está. La spec es la documentación de las decisiones, no del código.

## Archivos en este directorio

- [`specs/2026-04-05-legal-qa-agente-escribano.md`](specs/2026-04-05-legal-qa-agente-escribano.md)
  — Problema, decisiones de diseño, schema de datos, criterios de éxito, riesgos asumidos
- [`plans/2026-04-05-legal-qa-agente-escribano.md`](plans/2026-04-05-legal-qa-agente-escribano.md)
  — 10 tasks de implementación con archivos exactos, código esperado, y comandos de verificación
