# Skill: FastAPI endpoint

Lee este archivo completo antes de crear o modificar cualquier endpoint.

## Estructura de directorios

```
backend/
  main.py
  routers/
    chat.py
    ingest.py
    documents.py
  middleware/
    auth.py
    audit.py
  models/
    requests.py
    responses.py
  dependencies.py
```

Cada dominio tiene su propio router. Nunca pongas endpoints de distintos dominios
en el mismo archivo.

## Cómo importar el núcleo Python

El directorio `src/` está en el PYTHONPATH del backend. Importar así:

```python
from src.core.router import ask_unified
from src.analytics.ask_meta_sql import ask_metadata
from src.generators import crear_generador, tipos_disponibles
```

Nunca copiar código de `src/` al backend. Si algo de `src/` necesita cambiar
para adaptarse al backend, modificar `src/` directamente respetando las reglas
del CLAUDE.md.

## Autenticación con Clerk

Cada endpoint protegido recibe el JWT de Clerk en el header `Authorization: Bearer <token>`.
La verificación se hace en `middleware/auth.py` usando el SDK de Clerk para Python.

```python
from clerk_backend_api import Clerk
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

clerk = Clerk(bearer_auth=os.getenv("CLERK_SECRET_KEY"))
security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    try:
        claims = clerk.authenticate_request(credentials.credentials)
        return claims
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido"
        )
```

Roles disponibles: `admin`, `operator`, `reader`.
Los roles se guardan en los metadatos del usuario en Clerk y llegan en el JWT.

## Formato estándar de respuesta

Toda respuesta exitosa de `/chat` sigue este esquema Pydantic:

```python
class ChatResponse(BaseModel):
    answer: str
    source_type: Literal["sql", "rag", "generate"]
    conversation_id: str
    extra: dict = {}
```

Toda respuesta de error usa HTTPException con este formato en el detail:

```python
{"code": "ERROR_CODE", "message": "Descripción legible"}
```

Códigos de error del dominio:
- `CORPUS_EMPTY`: no hay escrituras indexadas
- `INGEST_FAILED`: error en pipeline de ingesta
- `GENERATION_INCOMPLETE`: datos insuficientes para generar documento
- `ROUTER_AMBIGUOUS`: el router no pudo clasificar la consulta

## Manejo de errores

```python
from fastapi import HTTPException
import logging

logger = logging.getLogger(__name__)

@router.post("/chat")
async def chat(body: ChatRequest, user=Depends(get_current_user)):
    try:
        result = ask_unified(body.message, ...)
        return ChatResponse(...)
    except Exception as e:
        logger.error("chat_error", extra={"user_id": user.id, "error": str(e)})
        raise HTTPException(status_code=500, detail={
            "code": "INTERNAL_ERROR",
            "message": "Error al procesar la consulta"
        })
```

Nunca exponer stack traces ni contenido de escrituras en respuestas de error.

## Variables de entorno requeridas por el backend

```
OPENAI_API_KEY=
CLERK_SECRET_KEY=
DATABASE_URL=          # Postgres connection string de Supabase
DATABASE_PATH=         # SQLite path para compatibilidad (data/notary.db)
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
```

## Tareas en background (ingesta)

Usar `BackgroundTasks` de FastAPI para la ingesta. No usar Celery ni Redis
en esta versión — es overhead innecesario para el volumen esperado (5k docs,
1-3 usuarios simultáneos).

```python
@router.post("/ingest")
async def ingest(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    user=Depends(get_current_user)
):
    job_id = str(uuid4())
    background_tasks.add_task(run_ingest_pipeline, job_id, file, user.id)
    return {"job_id": job_id, "status": "queued"}
```

El estado del job se persiste en la tabla `ingest_jobs` de Postgres.
