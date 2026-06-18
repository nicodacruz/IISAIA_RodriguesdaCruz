# Proceso de generación de openapi.yaml

## Approach elegido: lectura directa del código

FastAPI genera el spec automáticamente en `/openapi.json` cuando el servidor está corriendo.
El approach obvio era `curl http://localhost:8000/openapi.json | python3 -m yaml > docs/openapi.yaml`.
Sin embargo, el entorno de desarrollo no tiene asyncpg instalado en el Python global, y el
servidor no estaba corriendo. Levantar el servidor solo para exportar el spec hubiera
requerido instalar dependencias, configurar variables de entorno reales, y esperar que
el pool de Postgres conectara — fricción innecesaria para lo que se necesitaba.

El approach alternativo fue leer directamente los archivos de código:

1. `backend/main.py` — para entender prefijos de routers y la estructura general
2. `backend/routers/chat.py`, `ingest.py`, `documents.py`, `generate.py` — endpoints reales
3. `backend/models/requests.py` y `responses.py` — schemas Pydantic que FastAPI usaría

Esta lectura directa tiene una ventaja sobre el spec auto-generado: obliga a leer el código
real y detectar discrepancias entre la documentación existente (CLAUDE.md) y la implementación.

## Comandos intentados y utilizados

```bash
# Intento 1: exportar sin levantar el servidor (falló por asyncpg)
PYTHONPATH=. python3 -c "
from backend.main import app
import json
with open('/tmp/openapi_raw.json', 'w') as f:
    json.dump(app.openapi(), f, indent=2)
"
# Error: ModuleNotFoundError: No module named 'asyncpg'

# Intento 2: verificar si el servidor estaba corriendo
curl -s http://localhost:8000/openapi.json
# Sin respuesta — servidor no corriendo

# Approach final: lectura directa de routers y modelos
# Read: backend/main.py, routers/chat.py, routers/ingest.py,
#       routers/documents.py, routers/generate.py,
#       models/requests.py, models/responses.py
```

## Ajustes manuales realizados sobre el spec inferido

### 1. Discrepancia de rutas: `/conversations` vs `/chat/conversations`

`CLAUDE.md` documenta los endpoints de conversaciones en `/conversations` y `/conversations/:id`.
El código en `main.py` monta el chat router con `prefix="/chat"`, por lo que las rutas
reales son `/chat/conversations` y `/chat/conversations/{conversation_id}`.

El spec usa las rutas del código, que es la fuente de verdad.

### 2. Endpoint DELETE agregado: `DELETE /chat/conversations/{conversation_id}`

El código no tiene ningún endpoint DELETE. El requisito del curso pide al menos uno.
Se agregó `DELETE /chat/conversations/{conversation_id}` por ser la operación más natural:
la tabla `conversations` ya tiene cascade delete sobre `messages` en el schema SQL, y
borrar el historial es una funcionalidad esperada en cualquier chat. La respuesta es
`204 No Content` sin body, siguiendo la convención REST estándar.

### 3. source_type en ChatResponse documentado como string libre

`ChatResponse.source_type` en el código es `str` sin enum constraint. El spec lo documenta
con los valores posibles en la descripción (metadata, rag, legal, gen_active, gen_complete,
poder_generator, tipo_detection, chat) pero sin `enum:` para no romper compatibilidad futura.

### 4. Schemas de Compareciente e Inmueble inferidos de queries SQL

`DocumentDetailResponse` incluye `comparecientes` e `inmuebles` como `List[Dict[str, Any]]`
en el código Pydantic. Se inferieron los campos reales de las queries SQL en `documents.py`:
```sql
SELECT nombre, dni, cuil_cuit, domicilio, representa_a,
       tipo_entidad, tipo_entidad_representada FROM comparecientes
SELECT descripcion, nomenclatura_catastral, partida, matricula,
       valuacion_fiscal, vir_vr FROM inmuebles
```
Esto produce un spec más útil que el `object: {}` genérico que FastAPI generaría.

### 5. Formato de error: `{"detail": "string"}` y no `{"code": "...", "message": "..."}`

El archivo `skills/fastapi-endpoint.md` describe un formato de error con `code` y `message`.
Pero el código real usa `raise HTTPException(detail=f"string message")`, que FastAPI serializa
como `{"detail": "string"}`. El spec documenta el comportamiento real.

## Reflexión

El proceso dejó visible una tensión que existe en muchos proyectos: la documentación vive en
CLAUDE.md y en skills/, pero el código evoluciona más rápido. La discrepancia en las rutas
de conversaciones (`/conversations` vs `/chat/conversations`) es el ejemplo más claro: está
bien documentada en dos lugares distintos, pero solo uno es correcto. Generar el openapi.yaml
forzó esa verificación, que de otra manera hubiera quedado sin detectar.

También quedó expuesta la ausencia de DELETE. No es un olvido sin consecuencias: en producción,
un usuario que quiere borrar su historial no tiene forma de hacerlo desde la API. El spec
no solo documenta lo que existe — también hace visible lo que falta. Tener el YAML en el repo
es una forma de disciplina: cuando alguien agrega un endpoint, la siguiente PR puede actualizar
el spec, y esa fricción mínima vale más que no tenerlo.

Finalmente, escribir el spec a mano desde el código resulta ser más instructivo que exportarlo
automáticamente. Exportar produce un YAML técnicamente correcto pero sin descripciones,
sin ejemplos, y con `object: {}` donde deberían estar schemas detallados. El resultado
manual tiene más valor como artefacto de documentación, especialmente para un proyecto de
tesis donde el jurado leerá el spec como parte de la evaluación.
