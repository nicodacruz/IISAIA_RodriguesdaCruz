# Checkout Infernal — La peor UI posible

## Qué es

Esta página es un experimento de interfaz de usuario deliberadamente mala, inspirado en la idea de construir una UI funcional pero incómoda, confusa y frustrante.

El resultado es un checkout falso llamado **Checkout Infernal**. La página permite elegir una membresía, completar datos, aplicar un cupón, aceptar términos, calcular un total y agregar productos a un carrito. Es decir: funcionalmente se puede usar. El problema es que casi todas las decisiones de diseño están hechas para molestar al usuario.

## Qué hace la página

- Permite elegir entre tres membresías.
- Calcula subtotal, descuento, cargo raro y total.
- Tiene un cupón funcional: `porfavor`.
- Permite completar nombre, email y edad.
- Valida condiciones antes de comprar.
- Agrega productos a un carrito.
- Tiene modo oscuro.
- Muestra notificaciones y contador de errores.

## Por qué la UI es mala a propósito

Algunas decisiones anti-UX incluidas:

- El botón de compra se escapa cuando el usuario intenta tocarlo.
- El campo de nombre invierte el texto escrito.
- El campo de email reemplaza los puntos por texto.
- El slider de edad está visualmente invertido.
- El botón “-” suma cantidad y el botón “+” resta.
- El menú dice una cosa pero lleva a otra.
- Hay colores agresivos, bordes exagerados, animaciones molestas y textos poco claros.
- El progreso no llega nunca al 100%.
- Algunos botones existen solo para generar frustración.

## Archivos del repositorio

- `index.html`: página completa, con HTML, CSS y JavaScript en un solo archivo.
- `prompts.md`: secuencia de prompts usados y breve anotación de cada uno.
- `README.md`: explicación del proyecto, decisiones y aprendizajes.
