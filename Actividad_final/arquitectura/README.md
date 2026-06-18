# Arquitectura de NotarIA

El archivo [`architecture.md`](architecture.md) contiene los diagramas Mermaid del sistema:

- **Diagrama 1** — Flujo de una consulta: cómo un mensaje del usuario llega al frontend,
  se autentica, se clasifica por intent, se enruta a uno de 5 modos, y devuelve una respuesta
- **Diagrama 2** — Flujo de ingesta: cómo un PDF/DOC se convierte en markdown, se extrae
  metadata con LLM, y se indexa en pgvector

Los diagramas se renderizan automáticamente en GitHub y GitLab. Si los estás viendo en un
visor sin soporte Mermaid, podés renderizarlos en [mermaid.live](https://mermaid.live).
