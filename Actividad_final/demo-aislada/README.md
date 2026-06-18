# Demo aislada: validador de SQL

## Qué muestra

El script `sql_safety_demo.py` demuestra el validador de queries SQL que NotarIA aplica
antes de ejecutar cualquier query generada por el LLM contra la base de datos.

La lógica extraída es la función `validate_sql()` de
`src/analytics/text_to_sql/sql_generator.py`. Fue elegida como demo porque:

- Es **puro Python** — `frozenset` + comparación de strings. Sin imports externos.
- Es **directamente relevante** al diseño del sistema: el LLM genera SQL en lenguaje
  natural, pero no es confiable. El validador es la última barrera antes de ejecutar.
- **No necesita ninguna infraestructura**: cero pip installs, cero API keys, cero Postgres.

## Por qué esta pieza y no otra

Se evaluaron otras candidatas:

| Candidata | Por qué no |
|---|---|
| `intent_classifier` | Llama a OpenAI para clasificar — no aislable sin mock |
| Pipeline de ingesta | Requiere PyMuPDF, LibreOffice, OpenAI, Postgres |
| RAG search | Requiere pgvector con embeddings indexados |
| Frontend | Requiere Node.js + Next.js + backend corriendo |
| `validate_sql()` | **Pura Python, zero deps, relevante al dominio** ✓ |

## Cómo correr

```bash
python3 sql_safety_demo.py
```

Salida esperada:

```
======================================================================
NotarIA — Validador de SQL generado por LLM
======================================================================

Contexto: el LLM genera SQL a partir de lenguaje natural.
Antes de ejecutar contra la DB, validate_sql() verifica que
la query sea segura. Este es el resultado para cada caso:

  ✓ [OK] Conteo simple — 'cuántas escrituras hay'
      SQL: SELECT COUNT(*) FROM metadata
      Resultado: ACEPTADA

  ✓ [OK] Distribución por tipo — 'qué tipos de actos son más frecuentes'
      SQL: SELECT acto_caso, COUNT(*) FROM metadata GROUP BY acto_caso ORDER BY CO...
      Resultado: ACEPTADA

  ...

  ✓ [OK] Inyección clásica con semicolón + DROP
      SQL: SELECT 1; DROP TABLE metadata
      Resultado: RECHAZADA (Forbidden keyword: DROP)

  ...

----------------------------------------------------------------------
Resultado: 11/11 casos correctos

Todos los casos pasaron.
```

## Qué ilustra del diseño del sistema

El generador text-to-SQL de NotarIA tiene un diseño por capas:

1. **El LLM genera SQL** a partir de la pregunta del usuario + schema de la DB + lista
   de valores válidos de `acto_caso` (cargados desde `config/casos.yaml`)
2. **`validate_sql()` verifica** que la query sea read-only antes de ejecutarla
3. **`QueryExecutor` ejecuta** la query y detecta el tipo de resultado (count, list, aggregate)
4. **`ResponseGenerator` convierte** el resultado SQL en lenguaje natural para el usuario

La validación en el paso 2 es la que muestra este demo. La idea clave: el LLM es
instruccionable pero no 100% confiable — una barrera de código puro es más robusta
que confiar solo en el prompt para prevenir queries destructivas.

Los mismos casos del demo están cubiertos en `tests/test_sql_safety.py` con pytest
(30+ casos, incluyendo variantes con comentarios SQL, Unicode, y CTEs).
