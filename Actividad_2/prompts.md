# Prompts utilizados

A continuación se documenta el proceso de trabajo usado para construir el archivo `openapi.yaml`.

## Prompt 1 - Definición inicial de la API

```text
Quiero diseñar una API REST para un sistema llamado NotarIA. Es una aplicación para escribanías que permite subir escrituras notariales, procesarlas, extraer metadata y hacer consultas con un asistente de IA.

Necesito que me ayudes a pensar los recursos principales de la API antes de escribir el OpenAPI.

El sistema debería incluir:
- carga de documentos notariales;
- consulta del estado de ingesta;
- listado de escrituras procesadas;
- detalle de una escritura;
- conversaciones con un asistente;
- descarga de documentos generados.

No quiero todavía código backend. Solo quiero definir recursos REST, rutas y métodos HTTP.
```

## Resultado de la primera iteración

En esta primera etapa definí los recursos principales:

- `chat`
- `ingest`
- `documents`
- `generate`

La API todavía estaba bastante cerca de mi proyecto real, pero le faltaban algunos elementos pedidos por la consigna, sobre todo rutas con `DELETE` y una jerarquía de recursos más explícita.

## Prompt 2 - Adaptación a la consigna de OpenAPI

```text
Ahora quiero convertir esta idea en un archivo openapi.yaml válido.

La consigna pide:
- mínimo tres métodos HTTP: GET, POST y DELETE;
- jerarquía de recursos visible, por ejemplo un recurso anidado;
- al menos una respuesta de error 400 o 404 documentada;
- schemas tipados con type, required y format donde aplique;
- que el contrato pueda modificarse agregando endpoints sin reescribir todo.

Usá OpenAPI 3.1.0 y separá schemas, parameters y responses dentro de components.
También evitá usar nullable: true y representá los campos opcionales o nulos con tipos compatibles con JSON Schema, por ejemplo type: [string, "null"].
```

## Resultado de la segunda iteración

A partir de este prompt, la API quedó más alineada con REST. Se agregaron métodos `DELETE` para conversaciones, escrituras y comparecientes.

También se agregó una jerarquía más clara:

```text
/documents/{documentId}/parties
/documents/{documentId}/parties/{partyId}
/documents/{documentId}/questions
```

Esto permitió mostrar que los comparecientes y las preguntas pertenecen a una escritura determinada.

## Prompt 3 - Corrección de consistencia REST

```text
Revisá el contrato OpenAPI como si fueras un arquitecto backend.

Quiero que me marques problemas de consistencia REST, nombres poco claros, errores faltantes o schemas que estén demasiado sueltos.

También quiero que mejores:
- nombres de parámetros;
- respuestas de error reutilizables;
- schemas con required;
- formatos como uuid, date y date-time;
- enums donde tenga sentido.
```

## Resultado de la tercera iteración

En esta revisión se mejoraron varios puntos:

- se movieron parámetros repetidos a `components/parameters`;
- se agregaron responses reutilizables;
- se documentaron errores `400`, `401`, `404` y `422`;
- se agregaron campos `required`;
- se usaron formatos como `uuid`, `date`, `date-time` y `binary`;
- se adaptaron los campos nulos al estilo de OpenAPI 3.1.0, evitando `nullable: true`;
- se agregaron enums para estados y roles.

## Prompt 4 - Ajuste final para que no parezca una API genérica

```text
Quiero que el contrato no parezca un ejemplo genérico de tareas o proyectos.

Adaptalo al dominio de NotarIA, que trabaja con escrituras notariales, comparecientes, inmuebles, metadata, ingesta documental y consultas asistidas por IA.

Mantené la API simple, porque la actividad no pide implementar todo el backend. El foco tiene que estar en el contrato OpenAPI.
```

## Resultado final

La versión final mantiene el dominio real de NotarIA, pero sin entrar en detalles internos de implementación como base de datos, embeddings, workers, autenticación avanzada o deploy.

El archivo final define un contrato claro para una API REST y cumple con los puntos pedidos en clase:

- `GET`, `POST` y `DELETE`;
- recursos anidados;
- errores documentados;
- schemas tipados;
- estructura modular para poder iterar.
