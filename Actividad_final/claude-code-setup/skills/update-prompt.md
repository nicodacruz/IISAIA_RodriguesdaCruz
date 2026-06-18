# Skill: Iterar sobre prompts del sistema

Lee este archivo completo antes de editar cualquier archivo en `config/prompts/`.

Los prompts en `config/prompts/` son la primera palanca de mejora cuando el sistema
clasifica mal o responde de forma incorrecta. El código Python es la última. Esta skill
evita el error de editar el archivo incorrecto y te guía para confirmar que el cambio
funcionó — los tests de CI mockean el LLM y no capturan cambios de prompt.

---

## Paso 1 — Identificar el use_case que está fallando

Mapeá el síntoma al archivo a editar. Hay **12 archivos** en `config/prompts/`:

| Síntoma observado | Use-case | Archivo(s) a editar |
|---|---|---|
| Router manda algo a `sql` cuando debería ir a `legal_qa`, `qa` u otro modo | `intent_classifier` | `intent_classifier_system.txt` |
| Router clasifica mal el `chat_intent` (saludo, capacidades, etc.) | `intent_classifier` | `intent_classifier_system.txt` |
| El intent classifier extrae mal `file_id` o `acto_caso` del mensaje | `intent_classifier` | `intent_classifier_user.txt` |
| RAG responde sin citar fuentes o sintetiza mal el contexto | `rag_synthesizer` | `rag_system.txt` |
| Agente escribano (badge LEX) da respuesta jurídica incorrecta o inventa artículos | `legal_qa` | `legal_qa_system.txt` |
| La query SQL generada es incorrecta o filtra mal | `sql_generator` | `sql_generator_system.txt` |
| El formato de la query SQL no incluye los campos correctos | `sql_generator` | `sql_generator_user.txt` |
| La respuesta en lenguaje natural que envuelve el resultado SQL es mala | `response_generator` | `response_generator_system.txt` |
| La respuesta SQL es larga o mal formateada para el usuario | `response_generator` | `response_generator_user.txt` |
| La extracción de metadata de una escritura falla en campos específicos | `metadata_extraction` | `metadata_extract_system.txt` |
| La clasificación del `acto_caso` de una escritura es incorrecta | `classification` | `metadata_classify_system.txt` |
| El extractor no construye bien el JSON de metadata | `metadata_extraction` | `metadata_extract_user.txt` |

**Casos sin archivo de prompt** (prompt hardcodeado en Python, no editar por aquí):
- Respuestas del modo `chat` para saludos / capacidades → `src/core/router.py` función `_answer_from_chat()`
- Prompts del generador conversacional (preguntas campo a campo) → `src/generators/generators.py`

---

## Paso 2 — Distinguir system prompt vs user prompt

Casi todos los use_cases tienen dos archivos:

**`*_system.txt`** — define el rol, el tono y las restricciones del LLM:
- Qué es el asistente, qué puede y qué no puede hacer
- Reglas de formato de respuesta
- Ejemplos de comportamiento correcto e incorrecto
- **Editar aquí cuando:** el modelo responde con el tono incorrecto, sigue un patrón
  erróneo repetidamente, o no respeta una restricción importante

**`*_user.txt`** — template del mensaje del usuario con variables sustituidas en runtime:
- Contiene placeholders como `{question}`, `{schema_values}`, `{conversation_history}`
- Define la estructura del input que recibe el LLM
- **Editar aquí cuando:** el LLM no tiene acceso a información que debería tener
  (p.ej. el schema de la DB no le está llegando bien, o el contexto de conversación
  está mal formateado)

**Regla práctica:** editar el system primero. El user template casi nunca necesita cambios
a menos que agregues un nuevo campo de contexto.

---

## Paso 3 — El ciclo de iteración

```bash
# 1. Editar el archivo de prompt identificado en el paso 1
# Ejemplo: mejorar la clasificación de legal_qa
# editor config/prompts/intent_classifier_system.txt

# 2. Testear con la query que fallaba originalmente
python cli.py ask "cuáles son los requisitos formales de una escritura pública"
# Observar: ¿el source_type cambió a "legal"?

# 3. Testear con variantes de la misma query para verificar que no rompiste otros casos
python cli.py ask "cuántas escrituras hay"          # debe seguir yendo a sql
python cli.py ask "qué dice el contrato 20-0287"   # debe seguir yendo a qa

# 4. Si el comportamiento mejoró, correr los tests de CI
pytest tests/ -x -q
# Los tests mockean el LLM → no detectan cambios de prompt,
# pero sí detectan regresiones en la lógica de routing y procesamiento

# 5. Testear una query diferente del mismo tipo para confirmar generalización
python cli.py ask "qué necesito para cancelar una hipoteca"  # también debe ir a legal_qa
```

**El CLI muestra el `source_type`** de cada respuesta. Si no lo muestra explícitamente,
agregá `--verbose` o revisá la respuesta — el badge (SQL/RAG/LEX/GEN/CHAT) corresponde
al source_type devuelto.

---

## Paso 4 — Cuándo escalar a código

Si después de 2-3 iteraciones de prompt el comportamiento no mejoró:

**Problema en el clasificador de intenciones:**
Abrir `src/core/intent_classifier.py` — la función `_validate_and_sanitize()` tiene
lógica de fallback que puede estar sobreescribiendo la decisión del LLM. Por ejemplo,
si el modelo devuelve un modo que no está en `valid_modes`, lo reemplaza por `"sql"`.

**Problema en el router:**
Abrir `src/core/router.py` — la función `ask_unified()` tiene condiciones explícitas
sobre el orden de evaluación de modos. Si `legal_qa` se evalúa antes de `sql` en el
código pero el intent classifier devuelve `sql`, el modo correcto nunca se alcanza.

**Problema en RAG (respuesta pobre a pesar de chunks relevantes):**
Verificar primero si los chunks recuperados son relevantes:
```bash
python cli.py rag-search "requisitos escritura pública" --k 6
```
Si los chunks son buenos pero la síntesis es mala → problema de prompt.
Si los chunks son malos → problema de embeddings o de threshold, no de prompt.

**Referencia rápida de archivos de lógica:**

| Componente | Archivo |
|---|---|
| Clasificación de intención | `src/core/intent_classifier.py` |
| Router principal | `src/core/router.py` |
| Búsqueda RAG escrituras | `src/rag/search.py` |
| Búsqueda RAG normativa | `src/rag/search.py :: query_legal_index()` |
| Text-to-SQL Postgres | `src/analytics/text_to_sql/sql_generator.py` |
| Síntesis SQL en NL | `src/analytics/text_to_sql/response_generator.py` |
| Extracción de metadata | `src/ingest/metadata.py` |
