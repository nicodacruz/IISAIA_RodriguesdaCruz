# Skill: Agregar un nuevo tipo de escritura

Lee este archivo completo antes de agregar cualquier tipo de escritura al sistema.

El sistema es 100% data-driven: `UniversalGenerator` detecta los tipos disponibles en tiempo
de arranque leyendo los YAMLs. Si los tres pasos de este proceso están correctos, el nuevo
tipo funciona sin tocar código Python. Si alguno falla silenciosamente, el generator simplemente
no encontrará el tipo y el router responderá que no tiene conversacional implementado.

---

## Paso 1 — Verificar que el tipo no existe ya

```bash
python scripts/validate_config.py
```

Si pasa sin errores, el estado actual es coherente. Luego buscar el acto_caso candidato:

```bash
grep -r "nombre_del_tipo_candidato" config/casos.yaml config/escrituras_config.yaml
```

Si ya aparece en `casos.yaml` pero no en `escrituras_config.yaml`, el tipo existe en la
taxonomía pero no tiene template implementado. El trabajo es solo pasos 3 y 4.
Si no aparece en ninguno, hacer los cuatro pasos.

---

## Paso 2 — Agregar la entrada en `config/casos.yaml`

La taxonomía tiene tres niveles: `acto_clase` → `acto_subclase` → `acto_caso`.
El `acto_caso` es el identificador único que usa todo el sistema.

**Formato real** (basado en las entradas existentes):

```yaml
taxonomia:
  instrumento_publico_notarial:   # acto_clase existente
    escritura_publica:            # acto_subclase existente
      cesion_creditos:            # ← tu nuevo acto_caso (snake_case)
        descripcion: "Cesión de créditos"
        keywords:
          - "cesión de créditos"
          - "cesión de crédito"
          - "acreedor cedente"
        requiere_inmueble: false
```

**Reglas:**
- El `acto_caso` debe ser `snake_case` y único en todo el archivo
- `keywords` es lo que usa el intent classifier para detectar el tipo — incluir variantes
  del nombre tal como aparecen en el texto de las escrituras
- `requiere_inmueble: true` solo si el acto siempre incluye un bien raíz
- No inventar `acto_clase` ni `acto_subclase` nuevos sin discutirlo — la taxonomía refleja
  el dominio notarial real y tiene estructura legal

Si el tipo que necesitás entra en una `acto_subclase` que no existe aún, agregar la
subclase siguiendo el mismo patrón de indentación.

**Verificar:**

```bash
python scripts/validate_config.py
```

---

## Paso 3 — Agregar la entrada en `config/escrituras_config.yaml`

Aquí se define qué datos necesita el generador conversacional para este tipo.

**Formato real** (basado en `revocacion_poder` como ejemplo completo):

```yaml
templates:
  cesion_creditos:              # ← debe coincidir exactamente con el acto_caso en casos.yaml
    nombre: "Cesión de Créditos"
    descripcion: "Cesión total o parcial de derechos creditorios"
    template_file: "cesion_creditos.j2"    # nombre del archivo que crearás en el paso 4
    conversational: true

    campos_requeridos:
      - nombre: "cedente"
        tipo: "Compareciente"
        requerido: true
        prompt: "Datos del CEDENTE (quien transfiere el crédito)"
        hint: "Nombre completo, DNI/CUIT, domicilio"

      - nombre: "cesionario"
        tipo: "Compareciente"
        requerido: true
        prompt: "Datos del CESIONARIO (quien recibe el crédito)"

      - nombre: "credito_original"
        tipo: "ReferenciaEscritura"
        requerido: true
        prompt: "Datos del CRÉDITO a ceder"
        hint: "Instrumento de origen, fecha, monto"

      - nombre: "precio"
        tipo: "Dinero"
        requerido: false
        prompt: "PRECIO de la cesión (si es onerosa, dejar vacío si es gratuita)"
        default: null

      - nombre: "fecha"
        tipo: "Fecha"
        requerido: false
        prompt: "Fecha de la escritura (dejar vacío = hoy)"
        default: "HOY"

      - nombre: "numero_escritura"
        tipo: "String"
        requerido: false
        prompt: "Número de escritura (dejar vacío para completar luego)"
        default: null
```

**Tipos de campo disponibles** (definidos en la sección `tipos_datos` del mismo YAML):

| Tipo | Uso |
|---|---|
| `Compareciente` | Persona física o jurídica que comparece |
| `List[Compareciente]` | Varios comparecientes (vendedores, compradores, etc.) |
| `Inmueble` | Bien raíz con nomenclatura, matrícula, partida |
| `Precio` | Monto + moneda + forma de pago |
| `ReferenciaEscritura` | Referencia a escritura anterior (número, fecha, escribano, registro) |
| `Dinero` | Monto con moneda, sin forma de pago |
| `Boolean` | true/false |
| `String` | Texto libre |
| `Fecha` | ISO date o "HOY" |

**Regla de `requerido`:** si el campo puede omitirse (tiene un `default` o es opcional
según el tipo de acto), poner `requerido: false`. El generador preguntará igual pero
permitirá saltear con el comando "saltar".

---

## Paso 4 — Crear la template Jinja2 en `src/generators/templates/`

Crear el archivo `.j2` con el nombre exacto que pusiste en `template_file`.

**Advertencia crítica sobre los nombres de variables:**
Las variables disponibles en el template NO siempre coinciden con los `nombre` de los
`campos_requeridos`. El `UniversalGenerator` construye objetos Python tipados a partir
de los datos recolectados y los pasa a Jinja2 con nombres que pueden diferir del config.

Antes de escribir una template nueva, **leer juntos** el par de un tipo similar:
- `config/escrituras_config.yaml` (entrada del tipo) + su `.j2` en templates/

Por ejemplo, `revocacion_poder` tiene el campo `revocante` en el config pero la template
usa `{{ poderdante.xxx }}`. Y `hipoteca_cancelacion` tiene `deudor` en el config pero la
template usa `{{ compareciente.xxx }}`. Esta es una deuda técnica documentada del sistema.

**Estructura mínima de una template** (basada en los patrones comunes a las 6 existentes):

```jinja2
{{ gestor.titulo_acto() }} ESCRITURA NÚMERO __________.- {{ gestor.formula_apertura() }}
{{ gestor.formula_comparecencia() }}
{{ cedente.nombre_completo_formateado()|subrayar }},
{{ cedente.nacionalidad }},
{{ cedente.estado_civil_formateado() }},
titular del Documento Nacional de Identidad número {{ cedente.dni }},
C.U.I.T. número {{ cedente.cuil_cuit if cedente.cuil_cuit else '[___]' }},
con domicilio en {{ cedente.domicilio_completo() }},
{{ gestor.fe_conocimiento() }}, EXPONE:
[... cuerpo del acto ...]
{{ gestor.formula_cierre() }}
```

**Métodos disponibles en objetos `Compareciente`:**
- `.nombre_completo_formateado()` — nombre en mayúsculas con formato legal
- `.nacido_o_nacida()` — "nacido" o "nacida" según género
- `.estado_civil_formateado()` — "soltero", "casado con X", etc.
- `.domicilio_completo()` — dirección + localidad + provincia
- `.cuil_cuit`, `.dni`, `.nacionalidad`, `.profesion`, `.fecha_nacimiento`

**Filtros Jinja2 disponibles:**
- `|subrayar` — formatea el nombre en estilo escritura notarial
- `|fecha_a_letras(mayusculas=False)` — convierte una fecha a texto ("15 de abril de 2026")

La template más corta y simple como referencia de estructura es `revocacion_poder.j2`.
La más compleja (con lógica condicional y múltiples comparecientes) es `cancelacion_hipoteca.j2`.

---

## Paso 5 — Verificar que todo funciona

```bash
# 1. Validar que los YAMLs son coherentes
python scripts/validate_config.py

# 2. Verificar que el sistema detecta el nuevo tipo
python3 -c "
from src.generators import tipos_disponibles
tipos = tipos_disponibles()
print([k for k in tipos if 'cesion' in k])
"

# 3. Probar el flujo conversacional completo
python cli.py ask "generar una cesión de créditos"
# Debe responder iniciando el flujo conversacional, no "tipo no reconocido"
```

Si el paso 3 devuelve que el tipo no tiene sistema conversacional implementado, verificar:
1. Que `conversational: true` está en `escrituras_config.yaml`
2. Que el `acto_caso` en `escrituras_config.yaml` coincide exactamente con el de `casos.yaml`
3. Que `template_file` apunta a un archivo que existe en `src/generators/templates/`

Si hay un error en la template Jinja2 (variable no encontrada, método que no existe),
el error aparece en el log del backend al momento de generar el DOCX — no al inicio del
flujo conversacional. Testear hasta el final del flujo para detectarlo.
