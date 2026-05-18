# NotarIA API - Contrato OpenAPI

Este ejercicio define el contrato de una API REST para **NotarIA**, un sistema pensado para asistir a escribanías en la gestión documental de escrituras notariales.

NotarIA surge como una herramienta para trabajar con documentación notarial, especialmente escrituras. La idea general del proyecto es permitir que una escribanía pueda cargar documentos, procesarlos, extraer información relevante y luego consultar esa información de forma más simple. Por ejemplo, el sistema podría ayudar a identificar el tipo de acto, las partes intervinientes, los inmuebles mencionados, la fecha, el lugar, el escribano actuante y otros datos útiles para organizar o buscar documentos.

Además de la gestión documental, el proyecto contempla una capa de consulta asistida por IA. Esto permitiría hacer preguntas sobre la documentación cargada, consultar metadata estructurada o generar respuestas a partir del contenido de una escritura específica. Para esta actividad no se implementa esa lógica interna, sino que se modela cómo debería exponerse el sistema a través de una API REST.

## Objetivo de la actividad

El objetivo de esta entrega no fue implementar el backend completo, sino diseñar el contrato de la API usando **OpenAPI 3.1.0**.

El archivo `openapi.yaml` funciona como una especificación previa a la implementación. Es decir, describe cómo deberían ser las rutas, los métodos HTTP, los datos de entrada, las respuestas y los posibles errores, sin entrar en detalles internos como base de datos, autenticación real, embeddings, modelos de IA o despliegue.

La intención fue practicar cómo describir una API de forma clara, dejando definidos:

- recursos principales;
- métodos HTTP;
- rutas;
- parámetros;
- cuerpos de request;
- respuestas esperadas;
- errores posibles;
- schemas tipados.

## Recursos modelados

La API se organizó alrededor de los siguientes recursos:

- `chat`: consultas al asistente y conversaciones del usuario.
- `ingest`: carga de escrituras y seguimiento del estado de procesamiento.
- `documents`: consulta y gestión de escrituras procesadas.
- `parties`: comparecientes asociados a una escritura.
- `generate`: descarga de documentos generados.

Intenté que los nombres de las rutas representen recursos y no acciones. Por ejemplo, en vez de usar una ruta como `/deleteDocument`, la eliminación se expresa con el método `DELETE` sobre `/documents/{documentId}`.

## Endpoints principales

Algunos endpoints incluidos son:

- `GET /health`
- `POST /chat`
- `GET /chat/conversations`
- `GET /chat/conversations/{conversationId}`
- `DELETE /chat/conversations/{conversationId}`
- `POST /ingest`
- `GET /ingest/status/{jobId}`
- `GET /documents`
- `GET /documents/{documentId}`
- `DELETE /documents/{documentId}`
- `GET /documents/{documentId}/parties`
- `POST /documents/{documentId}/parties`
- `DELETE /documents/{documentId}/parties/{partyId}`
- `POST /documents/{documentId}/questions`
- `GET /generate/docx/{conversationId}`

## Cumplimiento de la consigna

El archivo cumple con los requisitos pedidos en clase.

### Tres métodos HTTP

Se incluyen, como mínimo:

- `GET`, para lectura de recursos.
- `POST`, para creación o envío de información.
- `DELETE`, para eliminación de recursos.

También se respeta la idea de que la acción no debe estar en el nombre de la ruta, sino en el método HTTP utilizado.

### Jerarquía de recursos

Se incluyen rutas anidadas como:

```text
/documents/{documentId}/parties
/documents/{documentId}/parties/{partyId}
/documents/{documentId}/questions
```

Esto permite representar que los comparecientes y las preguntas están asociados a una escritura específica.

### Respuestas de error

Se documentan respuestas de error como:

- `400 Bad Request`
- `401 Unauthorized`
- `404 Not Found`
- `422 Validation Error`

La intención fue no dejar solamente respuestas exitosas, sino también describir qué puede pasar cuando la solicitud está mal formada, falta autenticación, no se encuentra un recurso o fallan validaciones.

### Schemas tipados

Los schemas usan campos como:

- `type`
- `required`
- `format`
- `enum`
- `minLength`
- `maxLength`
- `minimum`
- `maximum`

Al usar OpenAPI 3.1.0, los campos que pueden ser nulos se expresan con tipos que incluyen `"null"`, por ejemplo:

```yaml
type:
  - string
  - "null"
```

Esto reemplaza el uso de `nullable: true`, que era más propio de OpenAPI 3.0.x.

### Iteración sobre el contrato

Durante el armado del archivo fui agregando endpoints sin reescribir todo desde cero. Para eso separé elementos reutilizables en `components`, como:

- `schemas`
- `parameters`
- `responses`
- `securitySchemes`

Esto facilita modificar o extender la API sin duplicar definiciones. Por ejemplo, si más adelante se quisiera agregar un endpoint para inmuebles, podría agregarse como recurso anidado de `documents` reutilizando parámetros y respuestas ya definidas.

## Decisiones de diseño

Una decisión importante fue mantener la API cerca de un caso real, en vez de inventar un ejemplo demasiado genérico. Por eso usé el dominio de NotarIA: escrituras notariales, ingesta documental, comparecientes, inmuebles, metadata y consultas asistidas por IA.

También intenté no mezclar el contrato con detalles de implementación. Por ejemplo, el YAML no define base de datos, lógica interna del modelo, sistema de embeddings, workers ni infraestructura. Solo describe cómo debería comunicarse un cliente con el backend.

Otra decisión fue agregar endpoints anidados para los comparecientes, porque es una forma clara de mostrar la relación entre una escritura y las personas que intervienen en ella. También agregué un endpoint para preguntas sobre una escritura específica, ya que representa bien el uso del asistente dentro del contexto documental.

## Dificultades encontradas

Una dificultad fue decidir cuánto detalle incluir. Si el contrato queda demasiado simple, no representa bien el sistema. Pero si se agregan demasiados detalles internos, empieza a parecer una implementación y no una especificación de API.

También tuve que revisar el uso de los métodos HTTP. Por ejemplo, las consultas se modelaron con `GET`, la creación de recursos o envío de información con `POST`, y las eliminaciones con `DELETE`.

Otro punto a cuidar fue la consistencia en los nombres. En una primera versión había rutas con nombres distintos para el mismo concepto, como `id`, `job_id` o `conversation_id`. En la versión final intenté usar nombres más consistentes en los parámetros de path, como `documentId`, `conversationId` y `jobId`.

Por último, al adaptar el archivo a OpenAPI 3.1.0, revisé los campos nulos para evitar depender de `nullable: true` y usar una forma más alineada con JSON Schema.

## Cómo visualizar el contrato

El archivo `openapi.yaml` puede visualizarse copiando su contenido en Swagger Editor o usando Swagger UI.

No hace falta implementar el backend para revisar este ejercicio, ya que el foco está puesto en el diseño del contrato.
