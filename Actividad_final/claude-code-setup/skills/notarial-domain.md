# Skill: Dominio notarial argentino

Lee este archivo completo antes de generar cualquier código que involucre
datos de escrituras, queries al corpus, o respuestas al usuario.

## Glosario esencial

**Escritura pública:** instrumento legal argentino otorgado ante escribano público.
Tiene estructura fija y valor probatorio pleno. No inventar campos ni términos.

**Compareciente:** persona física o jurídica que comparece ante el escribano.
Puede actuar por sus propios derechos, como apoderado de otro, o solo para
prestar asentimiento conyugal. Un mismo compareciente puede actuar en más
de un carácter simultáneamente (ej: por sí mismo Y como apoderado de dos personas).

**Asentimiento conyugal:** comparecencia de un cónyuge que no es parte de la
operación pero debe consentirla por afectar un bien ganancial. El compareciente
de asentimiento NO es parte vendedora ni compradora. Tiene campos propios:
`rol: "asentimiento"`, nunca confundirlo con otorgante o beneficiario.

**Acto notarial:** la operación jurídica que documenta la escritura.

**Acto caso:** el tipo específico dentro de la taxonomía de tres niveles.
Es el campo más granular y el que se usa para filtrar en SQL.

**Notario / escribano:** el profesional que autoriza el acto. En Argentina
se usa "escribano" en la UI, nunca "notario". El campo interno se llama `notario`
y debe capturar nombre completo + matrícula. Ejemplo: `"Agustín Mihura Gradin Mat. 5109"`.
El escribano autorizante firma con sello al final. A veces un escribano subrogante
expide la copia: son distintos, capturar solo el autorizante.

**Inmueble en CABA:** nomenclatura catastral con formato
`Circunscripción N, Sección N, Manzana N, Parcela N`.
Puede tener Unidad Funcional (UF) y Unidad Complementaria (UC) en propiedad horizontal.
Tiene Partida Inmobiliaria (ej: `1.452.350 DV 06`), Valuación Fiscal Homogénea,
y VIR (Valor Inmobiliario de Referencia). Matrícula formato: `FR 9-655/16`.

**Inmueble en Provincia:** nomenclatura catastral distinta según jurisdicción.
Puede incluir Circunscripción, Sección, Manzana, Quinta, Parcela, Subparcela,
y Polígonos. Para campos rurales: medidas en hectáreas/áreas/centiáreas,
linderos con coordenadas. Matrícula incluye el partido: `77.536 UF 2 del partido de LA MATANZA (70)`.
Capturar el campo `jurisdiccion` (ej: `"Entre Ríos"`, `"La Matanza, Buenos Aires"`).

**file_id:** identificador interno del documento.
Formato: `"20-0287"` (año-número), o con sufijo `"20-0298TER"`, `"25-0026BIS"`.
Es TEXT, no número. Siempre entre comillas. El sufijo BIS/TER/QUATER es parte
del file_id, nunca ignorarlo.

**Registro Notarial:** número de registro del escribano autorizante.
Aparece como "Registro Notarial 222", "Registro Notarial 137", etc.
Capturarlo en `notario_registro`. Es distinto de la matrícula del escribano.

**Folio:** número de folio del protocolo donde se asienta la escritura.
Aparece como "al folio 96", "al folio 1.254". Capturar en `folio`.

**COTI:** Código de Oferta de Transferencia de Inmuebles. Número obligatorio
para inmuebles de CABA que superan cierto valor. Aparece en las constancias
notariales al final. Capturar si está presente.

**Letra Hipotecaria Escritural:** instrumento creado por la Ley 24.441,
distinto a la hipoteca común. Cuando se cancela, el documento menciona
tanto la cancelación de la hipoteca como la extinción de la letra.
El `acto_caso` es `hipoteca_cancelacion` en ambos casos, pero el campo
`tiene_letra_hipotecaria` debe ser `true`.

**PEP (Persona Expuesta Políticamente):** declaración jurada que aparece
en actos societarios. El compareciente declara si está o no en la nómina de PEP
según Resolución UIF 11/2011. Nunca loggear este dato. Capturarlo como
`declaracion_pep: true/false` en el compareciente que lo declara.

**Precio en moneda extranjera:** frecuente en operaciones inmobiliarias.
Capturar moneda (ARS/USD) y monto por separado. Ejemplo:
`precio_monto: 525000`, `precio_moneda: "USD"`.

## Taxonomía de casos

La taxonomía completa está en `config/casos.yaml`. Tiene tres niveles:

```
acto_clase → acto_subclase → acto_caso
```

Ejemplos representativos del corpus real:
```
instrumento_publico_notarial
  └── escritura_publica
        ├── compraventa_inmueble
        ├── permuta_inmueble          ← dos partes intercambian inmuebles
        ├── donacion_inmueble
        ├── poder_general_adm_y_judicial
        ├── poder_asentimiento
        ├── revocacion_poder
        ├── hipoteca_constitucion
        ├── hipoteca_cancelacion      ← puede incluir letra hipotecaria
        └── cesion_derechos
procedimiento_conexo
  └── registro_acta_societaria
        └── transcripcion_acta_designacion_autoridades  ← actos de S.A.
```

Nunca hardcodear valores de `acto_caso`. Siempre cargar desde
`config_loader.get_taxonomia()` o `config_loader.get_all_acto_casos()`.

## Estructura real de un compareciente

Un compareciente puede tener múltiples roles en el mismo acto.
El campo `rol` acepta estos valores (pueden ser múltiples):

```python
roles_validos = [
    "propio_derecho",      # actúa por sí mismo
    "apoderado",           # actúa en representación de otro
    "representante_sa",    # representa a una S.A. u otra persona jurídica
    "asentimiento",        # solo presta asentimiento conyugal, no es parte
]
```

Ejemplo de compareciente con rol múltiple (caso `25-0023`):
```json
{
  "nombre": "Diego Marcos RIPA",
  "dni": "16202730",
  "cuil_cuit": "20-16202730-2",
  "domicilio": "Gorriti 445, Avellaneda, Provincia de Buenos Aires",
  "roles": ["propio_derecho", "apoderado"],
  "representa_a": [
    {
      "nombre": "Paula Silvina RIPA",
      "dni": "20636911",
      "poder_escritura": "352",
      "poder_registro": "222",
      "poder_fecha": "2022-12-05"
    },
    {
      "nombre": "Marta MIGUENS",
      "dni": "2925455",
      "poder_escritura": "128",
      "poder_registro": "222",
      "poder_fecha": "2022-06-03"
    }
  ]
}
```

## Estructura de acreditación para personas jurídicas

Cuando un compareciente representa a una S.A. u otra PJ, acredita
la representación con múltiples instrumentos en cadena:
1. Estatuto social (escritura de constitución + inscripción IGJ)
2. Reformas de estatuto (si las hay)
3. Acta de asamblea de elección de autoridades
4. Acta de directorio de distribución de cargos

Capturar en `acreditacion_representacion` como lista ordenada.
El dato más relevante para búsqueda es el CUIT de la PJ y su denominación.

```json
{
  "nombre": "Jorge Omar PANELLI",
  "rol": "representante_sa",
  "representa_pj": {
    "denominacion": "ESABEM SOCIEDAD ANONIMA",
    "cuit": "30-67814796-2",
    "cargo": "Presidente del Directorio"
  },
  "declaracion_pep": false
}
```

## Constancias notariales frecuentes

Al final de cada escritura el escribano deja constancias. Las más comunes:

- **Certificado de Bienes Registrables:** hoy derogado por RG 2371/2007 AFIP.
  Si aparece la mención de su derogación, no capturarlo como certificado presente.
- **Certificado de dominio:** del Registro de la Propiedad. Capturar número.
- **Certificado de inhibición:** del Registro de la Propiedad. Capturar número.
- **COTI:** solo para CABA, inmuebles de alto valor. Capturar número si aparece.
- **Impuesto a la Transferencia de Inmuebles (ITI):** puede estar exento
  si es vivienda única. Capturar monto o constancia de exención.
- **Impuesto de Sellos CABA o Provincia:** capturar monto.
- **Autorización a escribano de otra jurisdicción:** para gestionar inscripción
  en registro provincial. Capturar nombre del escribano autorizado y jurisdicción.

## Modos del router

El router clasifica cada consulta en uno de tres modos:

**`sql`** — consultas estructuradas sobre metadata:
- "¿Cuántas escrituras hay?"
- "¿Qué escrituras son de 2023?"
- "¿Cuántos poderes se otorgaron este año?"
- "Dame el detalle de la escritura 20-0287"
- "¿En qué escrituras aparece el Banco de Galicia?"
- Cualquier conteo, filtro, ranking, o porcentaje

**`qa`** — preguntas sobre contenido semántico del texto:
- "¿Qué facultades tiene el apoderado en 20-0286?"
- "¿Qué condiciones tiene la cancelación de hipoteca 25-0023?"
- "¿En qué escrituras se menciona usufructo vitalicio?"
- Cualquier pregunta sobre cláusulas, condiciones, o interpretación

**`generate_escritura`** — pedido de generar un nuevo documento:
- "Quiero generar un poder general"
- "Necesito hacer una cancelación de hipoteca"
- "Generá una permuta de inmuebles"

La UI muestra el modo (badge SQL / RAG / GEN) sin que el usuario lo entienda.

## Campos obligatorios vs opcionales

**Siempre presentes** en una escritura correctamente extraída:
- `file_id`, `acto_clase`, `acto_subclase`, `acto_caso`
- `lugar` (default: `"Ciudad de Buenos Aires"`)
- Al menos un compareciente con `nombre`
- `notario` (nombre + matrícula del autorizante)

**Frecuentemente presentes** pero opcionales:
- `fecha_iso`, `folio`, `notario_registro`
- `inmueble` (solo si el acto involucra un bien raíz)
- `comparecientes[].dni`, `comparecientes[].cuil_cuit`
- `precio_monto`, `precio_moneda`

**Presentes solo en casos específicos:**
- `tiene_letra_hipotecaria`: solo en `hipoteca_cancelacion`
- `declaracion_pep`: solo en actos societarios
- `coti`: solo en transferencias de inmuebles de CABA de alto valor
- `autoriza_escribano_jurisdiccion`: solo cuando hay autorización a otro escribano
- `jurisdiccion_inmueble`: cuando el inmueble está fuera de CABA

Si un campo obligatorio falta, marcarlo como `null` y continuar.
Nunca bloquear la ingesta por campos faltantes.

## Restricciones de confidencialidad

**Nunca loggear contenido de escrituras en texto plano.** Solo loggear `file_id`.

```python
# CORRECTO
logger.info("rag_query", extra={"file_ids": ["20-0287", "20-0315"]})

# INCORRECTO — nunca hacer esto
logger.info(f"chunk content: {chunk['document']}")
```

**El campo `declaracion_pep` nunca se expone en respuestas al usuario.**
Es dato interno de auditoría, no de consulta.

**Nunca exponer DNI, CUIL o CUIT completos en logs.**
En logs usar solo los últimos 4 dígitos si es necesario referenciar una persona.

**El corpus de escrituras reales nunca va al repositorio público.**
Para tests de CI usar solo el corpus sintético en `tests/fixtures/`.

## Ejemplos de queries válidas por modo

### SQL
```
"cuántas escrituras hay"
→ SELECT COUNT(*) FROM metadata

"escrituras de 2023"
→ WHERE anio = 2023

"cancelaciones de hipoteca del Banco de Galicia"
→ JOIN comparecientes WHERE tipo_entidad = 'banco'
  AND nombre ILIKE '%Galicia%'
  AND acto_caso = 'hipoteca_cancelacion'

"escrituras con inmuebles en Entre Ríos"
→ WHERE raw_json->>'jurisdiccion_inmueble' = 'Entre Ríos'

"detalle de 20-0298TER"
→ WHERE file_id = '20-0298TER'
```

### QA
```
"qué condiciones tiene la cancelación en 25-0023"
→ RAG con where file_id = '25-0023'

"escrituras donde aparece asentimiento conyugal"
→ RAG cross-document buscando comparecientes con rol 'asentimiento'

"qué facultades tiene el apoderado en 20-0286"
→ RAG con where file_id = '20-0286'
```

### Generate
```
"generar poder general"          → TipoEscritura.PODER_GENERAL_ADM_Y_JUDICIAL
"cancelación de hipoteca"        → TipoEscritura.HIPOTECA_CANCELACION
"permuta de dos inmuebles"       → TipoEscritura.PERMUTA_INMUEBLE
"poder de asentimiento conyugal" → TipoEscritura.PODER_ASENTIMIENTO
```

## Patrones de clasificación que confunden al LLM

Estos casos generan errores frecuentes en el extractor. Documentarlos
explícitamente en los prompts de clasificación:

1. **Transcripción de acta societaria:** el documento contiene actas literales
   transcriptas. El `acto_caso` es `transcripcion_acta_designacion_autoridades`,
   NO `acta_eleccion_autoridades` ni `designacion_autoridades`. El título siempre
   empieza con "TRANSCRIPCION DE ACTA DE...".

2. **Cancelación con letra hipotecaria:** el título dice "CANCELACIÓN de HIPOTECA
   y LETRA HIPOTECARIA ESCRITURAL". El `acto_caso` sigue siendo `hipoteca_cancelacion`.

3. **Permuta:** puede confundirse con compraventa porque involucra dos inmuebles
   y dos partes. La clave es que no hay precio en dinero sino intercambio de bienes.
   Buscar "PERMUTA" o "transferirse recíprocamente" en el título.

4. **Compareciente con múltiples roles:** cuando alguien actúa "por sus propios
   derechos y además como apoderado de...", son múltiples roles en un solo
   compareciente, no múltiples comparecientes.

5. **file_id con sufijo:** `"20-0298TER"` es un único file_id. El sufijo
   BIS/TER/QUATER indica que es una escritura adicional del mismo número
   (segunda, tercera, cuarta escritura con ese número en el protocolo).
   Nunca separar el sufijo del número.
