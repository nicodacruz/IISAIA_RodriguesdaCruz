# Spec: Agente Escribano — Consultas jurídicas sobre normativa notarial

**Fecha:** 2026-04-05
**Estado:** aprobado
**Autores:** equipo NotarIA

---

## Problema

Los escribanos argentinos necesitan resolver dudas jurídicas mientras trabajan: qué requisitos
exige el CCC para un acto de disposición, cómo funciona el tracto sucesivo, qué diferencia
hay entre un poder general y uno especial. Hoy resuelven eso buscando en PDFs de las leyes,
preguntando a colegas, o consultando manuales físicos.

NotarIA ya responde sobre el corpus de escrituras del propio escribano (qué dice la escritura
20-0287, cuántas compraventas hubo en 2023). Pero eso no cubre la otra mitad del trabajo
diario: las consultas de derecho notarial puro, que no dependen del corpus específico de esa
escribanía sino de la normativa vigente.

El gap concreto: un escribano que usa NotarIA para consultar sus propias escrituras hoy no
puede preguntarle "¿cuáles son los requisitos formales para una escritura pública según el
CCC?" sin que el sistema le diga que no encontró escrituras relevantes.

---

## Decisiones de diseño

### ¿Por qué un índice RAG separado y no el mismo índice de escrituras?

Las escrituras del corpus son documentos privados de la escribanía, particionados por
`user_id` (multi-tenancy). La normativa — CCC, Ley 404, Ley 17.801 — es pública y
compartida entre todos los tenants. Mezclar ambas en la misma tabla `embeddings` implica
o bien indexar la normativa por separado para cada tenant (desperdicio de almacenamiento
y embeddings equivalentes) o bien introducir una excepción a la regla de filtrado por
`user_id` (riesgo de bugs de aislamiento).

Decidimos crear la tabla `legal_embeddings` sin columna `user_id`. Es la representación
más honesta del dominio: estos chunks pertenecen a todos los usuarios por igual. El código
de búsqueda nunca recibe un `user_id` como parámetro — la ausencia del campo en la firma
hace imposible el error de pasar un tenant y filtrar erróneamente.

### ¿Por qué un system prompt especializado y no el chat genérico?

El system prompt genérico de NotarIA es agnóstico al modo y tono. El agente escribano
necesita comportarse de una forma muy específica: citar artículos concretos (no "el CCC
dice"), distinguir entre regla general y excepción, no dar asesoramiento impositivo, y
declarar explícitamente cuando no sabe. Un escribano real que use el sistema tiene
formación jurídica y espera respuestas al mismo nivel — un tono casual o ambiguo sería
peor que no tener la feature.

Optamos por externalizar el prompt en `config/prompts/legal_qa_system.txt` (mismo
patrón que el resto del sistema) en lugar de hardcodearlo en el código, para poder ajustarlo
sin tocar Python cuando cambia la normativa o cuando el feedback de los escribanos
sugiere calibraciones de tono.

### ¿Por qué pgvector y no búsqueda por keywords sobre los textos de ley?

Los textos legales usan vocabulario técnico estable, lo que favorece a los keywords. Pero las
consultas de los usuarios no: "qué necesito para vender un departamento" es semánticamente
equivalente a "requisitos para actos de disposición de inmuebles" (art. 1017 CCC), pero
no comparte ninguna palabra clave.

pgvector con embeddings text-embedding-3-small captura esa equivalencia semántica. El
costo de mantener el mismo sistema de búsqueda que ya usamos para las escrituras es bajo,
y la coherencia arquitectónica (un solo mecanismo de retrieval) reduce la superficie de
mantenimiento.

### ¿Qué normativa incluir en el índice inicial y por qué ese subset?

Incluimos ocho documentos en `data/legal_docs/`:

| Archivo | Justificación |
|---|---|
| `ccc_instrumentos_publicos.md` | Arts. 299-312 CCC: forma y requisitos de la escritura pública. Consulta más frecuente. |
| `ccc_mandato_poderes.md` | Arts. 362-381 CCC: capacidad, tipos de poder, revocación. Segundo tema más consultado. |
| `ccc_compraventa.md` | Arts. 1123-1171 CCC: precio, forma, tracto, saneamiento. Acto más común en el corpus. |
| `ccc_derechos_reales.md` | Arts. 1882-2276 CCC: dominio, condominio, superficie, usufructo, hipoteca. |
| `ccc_donacion.md` | Arts. 1542-1573 CCC: forma, aceptación, revocación. Tercer acto más común en el corpus. |
| `ccc_contratos_forma.md` | Arts. 1015-1020 CCC: libertad de formas, forma solemne relativa y absoluta. |
| `ley_404_caba.md` | Ley Notarial de CABA: requisitos del ejercicio profesional, protocolo, aranceles. |
| `ley_17801_registro_propiedad.md` | Tracto sucesivo, prioridades registrales, inhibiciones. |

Quedaron fuera en esta versión: Ley 19.550 (Ley General de Sociedades), resoluciones UIF
sobre lavado, normativa provincial distinta de CABA. El criterio de corte fue la frecuencia
de consulta esperada en una escribanía urbana de CABA, que es el perfil del cliente inicial.

---

## Arquitectura propuesta

```
Usuario (chat)
    │
    ▼
POST /chat {message}
    │
    ▼
classify_intent_llm()                         [intent_classifier.py]
    │
    ├─ mode = "legal_qa"  ──────────────────────────────────────────────┐
    │                                                                    │
    │  (La clave de clasificación: la pregunta es sobre DERECHO          │
    │   notarial general, no sobre escrituras del corpus.)              │
    │                                                                    ▼
    │                                             _answer_from_legal_qa()  [router.py]
    │                                                    │
    │                                                    ▼
    │                                          query_legal_index()       [search.py]
    │                                                    │
    │                                                    ▼
    │                                          search_legal_pg()         [indexer_pg.py]
    │                                          SELECT ... FROM legal_embeddings
    │                                          ORDER BY vector <=> $1
    │                                          LIMIT 8
    │                                                    │
    │                                                    ▼
    │                                          Construir contexto con [fuente]
    │                                          (source = stem del archivo .md)
    │                                                    │
    │                                                    ▼
    │                                          llm_answer_with_context() [rag/llm.py]
    │                                          system = legal_qa_system.txt
    │                                          temperature = 0.0
    │                                                    │
    │                                                    ▼
    │                                          AskResponse(source_type="legal")
    │
    ▼
ChatResponse → frontend: badge LEX (violeta)
```

**Degradación con gracia:** si pgvector no está disponible (DATABASE_URL ausente),
`query_legal_index()` lanza excepción, `_answer_from_legal_qa()` la captura, y el LLM
responde igual con su conocimiento entrenado — sin contexto RAG pero sin crash.

---

## Schema de datos

```sql
CREATE TABLE legal_embeddings (
    id          SERIAL PRIMARY KEY,
    source      TEXT NOT NULL,      -- stem del .md: "ccc_mandato_poderes", "ley_404_caba"
    chunk_ix    INTEGER NOT NULL,   -- posición del chunk dentro del documento
    content     TEXT NOT NULL,      -- texto del chunk (~500 tokens)
    vector      vector(1536) NOT NULL,  -- embedding OpenAI text-embedding-3-small
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (source, chunk_ix)       -- idempotencia en reindexación
);

-- Índice HNSW para búsqueda aproximada eficiente
CREATE INDEX idx_legal_embeddings_vector
    ON legal_embeddings
    USING hnsw (vector vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
```

**Por qué sin `user_id`:** la normativa argentina es pública. No existe el concepto de
"mi CCC" vs "tu CCC". Agregar `user_id` introduciría duplicación de filas idénticas
(mismos chunks para cada tenant), gasto de almacenamiento y embeddings redundantes, y
complejidad operacional sin ningún beneficio de aislamiento. La ausencia del campo
en el schema es una decisión activa, no un olvido.

**Por qué `UNIQUE (source, chunk_ix)`:** permite reindexar sin acumulación. El indexador
hace DELETE por source antes de insertar, pero el UNIQUE es la última barrera contra
duplicados si el proceso falla a mitad.

---

## Criterios de éxito

**Funcional:** el sistema puede responder correctamente estas consultas sin halucinar artículos:

| Query | Respuesta esperada |
|---|---|
| "¿Cuáles son los requisitos formales de una escritura pública?" | Arts. 299-312 CCC: intervención de escribano, protocolo, firma, numeración |
| "¿Qué diferencia hay entre un poder general y uno especial?" | Poder general: art. 375 CCC; especial: art. 362 — actos determinados |
| "¿Qué es el tracto sucesivo?" | Ley 17.801 art. 15: continuidad de titularidades en el registro |
| "¿Necesita asentimiento conyugal la venta de la casa propia?" | Depende del régimen patrimonial: arts. 456 y 470 CCC |
| "¿Qué plazo tiene el Registro de la Propiedad para expedir un certificado?" | Ley 17.801: 5 días hábiles para certificados |

**Clasificación:** el intent classifier debe enrutar a `legal_qa` y no a `qa` ni `sql` para al menos el 90% de las consultas jurídicas generales del conjunto de evaluación.

**Calidad de cita:** al menos el 80% de las respuestas deben incluir una referencia normativa
específica (número de artículo, nombre de ley) cuando la respuesta está basada en el contexto RAG.

---

## Riesgos y trade-offs asumidos

**1. El LLM puede responder igual sin RAG**
Si el contexto de `legal_embeddings` no aporta nada que el modelo no sepa (p.ej., el CCC
es parte del pretraining de GPT-4), el RAG solo agrega latencia y costo. El trade-off es
aceptable porque: (a) el RAG sí aporta cuando la consulta involucra normativa local poco
representada en pretraining (Ley 404 CABA, circulares del Colegio de Escribanos), y (b)
citar el chunk como fuente permite al usuario verificar la respuesta — algo que el modelo
solo no puede hacer.

**2. La clasificación `legal_qa` vs `qa` es frágil en el margen**
"¿Cuáles son los requisitos para una compraventa?" puede ser jurídica (legal_qa) o una
pregunta sobre el corpus ("¿qué compraventas hay en el sistema?", sql). El intent classifier
distingue por si la pregunta apunta al derecho general o a datos del corpus. Casos borde:
"¿Qué es una cancelación de hipoteca?" — el prompt del classifier tiene ejemplos explícitos
para reducir ambigüedad, pero habrá errores de clasificación.

**3. La normativa indexada es un snapshot**
Indexamos el texto de las leyes tal como estaban en abril 2026. El CCC puede sufrir reformas
parciales. La decisión fue aceptar este riesgo para el MVP y agregar en el roadmap un proceso
de actualización trimestral del índice cuando haya modificaciones legislativas.

**4. k=8 es mayor que el k=6 del RAG de escrituras**
Los textos normativos tienen chunks más densos y conceptualmente más cortos que los de
escrituras (que son narrativos). Con k=6 muchas consultas pierden el artículo específico
relevante. k=8 aumenta el contexto enviado al LLM pero mejora la cobertura. El costo en
tokens es aceptable dado que `temperature=0.0` y los chunks son compactos.

---

## Lo que queda fuera del scope

- **Ley 19.550 (Ley General de Sociedades):** relevante para actos societarios pero fuera
  del uso frecuente de una escribanía de CABA enfocada en inmuebles y poderes. Se agrega
  en una iteración posterior.
- **Normativa provincial:** solo CABA. Las escribanías de provincia tienen registros y
  normativa diferentes; requiere validación con usuarios reales antes de indexar.
- **Resoluciones UIF (lavado de dinero):** el sistema no debe convertirse en un asesor
  de compliance — ese riesgo legal excede el scope de un MVP.
- **Actualización automática del índice:** el proceso de reindexación es manual (`python cli.py legal-build`). Scrapers de ley o ingesta automática de reformas queda para una versión futura.
- **Búsqueda por número de artículo:** "¿qué dice el art. 1017?" con lookup exacto en el
  texto de la ley. El RAG semántico lo cubre implícitamente pero un usuario que cita el
  artículo por número merecería un lookup directo. Out of scope para este MVP.
