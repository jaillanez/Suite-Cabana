---
name: Marketplace turístico argentino (repo Suite-Cabana)
description: El estándar de la categoría ejecutado a fidelidad completa, con la identidad puesta en la precisión del número.
colors:
  fondo: "#ffffff"
  fondo-2: "#f6f6f7"
  fondo-3: "#ededf0"
  borde: "#e3e3e7"
  borde-fuerte: "#c6c6cd"
  texto: "#17171a"
  texto-2: "#56575f"
  texto-3: "#6e6f78"
  acento: "#145c4a"
  acento-fuerte: "#0e4237"
  acento-tenue: "#edf4f2"
  alerta: "#a32218"
  alerta-tenue: "#fcf0ef"
typography:
  display:
    fontFamily: "Archivo, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "clamp(1.875rem, 4.4vw, 3rem)"
    fontWeight: 600
    lineHeight: 1.08
    letterSpacing: "-0.03em"
  headline:
    fontFamily: "Archivo, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "1.375rem"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "-0.02em"
  title:
    fontFamily: "Archivo, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "1rem"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "-0.015em"
  precio:
    fontFamily: "Archivo, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.02em"
    fontFeature: "'tnum' 1"
  body:
    fontFamily: "Archivo, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "normal"
  body-sm:
    fontFamily: "Archivo, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 400
    lineHeight: 1.45
    letterSpacing: "normal"
  label:
    fontFamily: "Archivo, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "0.6875rem"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "0.04em"
rounded:
  s: "6px"
  md: "10px"
  l: "14px"
  pastilla: "999px"
spacing:
  "1": "0.25rem"
  "2": "0.375rem"
  "3": "0.5rem"
  "4": "0.625rem"
  "5": "0.75rem"
  "6": "1rem"
  "7": "1.25rem"
  "8": "1.5rem"
  "10": "2rem"
  "12": "3rem"
components:
  boton-buscar:
    backgroundColor: "{colors.acento}"
    textColor: "#ffffff"
    rounded: "{rounded.l}"
    padding: "0 1.25rem"
    typography: "{typography.body}"
  boton-buscar-hover:
    backgroundColor: "{colors.acento-fuerte}"
    textColor: "#ffffff"
  boton-aplicar:
    backgroundColor: "{colors.acento}"
    textColor: "#ffffff"
    rounded: "{rounded.s}"
    padding: "0.5625rem 1.125rem"
  boton-aplicar-hover:
    backgroundColor: "{colors.acento-fuerte}"
    textColor: "#ffffff"
  boton-secundario:
    backgroundColor: "{colors.fondo}"
    textColor: "{colors.texto}"
    rounded: "{rounded.s}"
    padding: "0.5rem 0.875rem"
  boton-secundario-hover:
    backgroundColor: "{colors.fondo-2}"
    textColor: "{colors.texto}"
  chip:
    backgroundColor: "{colors.fondo}"
    textColor: "{colors.texto}"
    rounded: "{rounded.pastilla}"
    padding: "0.375rem 0.75rem"
    typography: "{typography.body-sm}"
  chip-hover:
    backgroundColor: "{colors.fondo-2}"
    textColor: "{colors.texto}"
  chip-activo:
    backgroundColor: "{colors.acento}"
    textColor: "#ffffff"
    rounded: "{rounded.pastilla}"
  campo-barra:
    backgroundColor: "{colors.fondo}"
    textColor: "{colors.texto}"
    rounded: "{rounded.l}"
    padding: "0.5rem 0.875rem"
  campo-barra-focus:
    backgroundColor: "{colors.fondo-2}"
    textColor: "{colors.texto}"
  tarjeta-resultado:
    backgroundColor: "transparent"
    textColor: "{colors.texto}"
    rounded: "{rounded.l}"
    padding: "0.5rem"
  tarjeta-resultado-hover:
    backgroundColor: "{colors.fondo-2}"
    textColor: "{colors.texto}"
  panel-dialogo:
    backgroundColor: "{colors.fondo}"
    textColor: "{colors.texto}"
    rounded: "{rounded.l}"
    width: "min(560px, calc(100vw - 2rem))"
  pin-mapa:
    backgroundColor: "{colors.fondo}"
    textColor: "{colors.texto}"
    rounded: "{rounded.pastilla}"
    padding: "0.25rem 0.625rem"
    typography: "{typography.body-sm}"
  pin-mapa-activo:
    backgroundColor: "{colors.acento}"
    textColor: "#ffffff"
    rounded: "{rounded.pastilla}"
  insignia-inmediata:
    backgroundColor: "{colors.acento-tenue}"
    textColor: "{colors.acento}"
    rounded: "{rounded.s}"
    padding: "0.1875rem 0.5rem 0.1875rem 0.375rem"
  paginado-actual:
    backgroundColor: "{colors.texto}"
    textColor: "{colors.fondo}"
    rounded: "{rounded.s}"
    size: "34px"
  alternar-vista:
    backgroundColor: "{colors.texto}"
    textColor: "{colors.fondo}"
    rounded: "{rounded.pastilla}"
    padding: "0.6875rem 1.125rem"
---

# Design System: Marketplace turístico argentino

## Overview

**Creative North Star: "El mostrador que no miente"**

El equipo eligió explícitamente el estándar de la categoría por sobre las direcciones propias, con la vara declarada en Airbnb, Booking y Despegar (PRODUCT.md, 2026-09-16). Eso es una decisión registrada, no una falta de ambición: el viajero argentino comparando de noche en el teléfono tiene que reconocer el patrón en un segundo —barra de búsqueda persistente, chips de filtro, grilla de tarjetas con foto dominante, mapa con precios en los pines— y no gastar ni un latido en aprender un mundo visual nuevo. La convención es el compromiso y se ejecuta a fidelidad completa, sin ironía, sin guiños, sin un detalle raro metido para tener personalidad.

Con la forma prestada, la identidad se muda al único lugar donde se puede ganar: la precisión. El número más grande de la pantalla es el total real de esas fechas, en cifras tabulares, con el desglose abierto a un clic y sin cargos escondidos. Donde la categoría pone estrellas, acá va "Confirmación inmediata", que es un dato verdadero y verificado contra el calendario. No hay "desde $X", no hay contadores de urgencia, no hay reseñas inventadas. El ground es claro y casi blanco, el cromatismo está racionado a un solo verde profundo, y todo el peso visual lo cargan la foto del alojamiento y la cifra del precio.

La densidad es alta pero aireada: texto base de 15px, tipografía de trabajo (Archivo, de Omnibus-Type, Buenos Aires) con cifras tabulares parejas, grises de tres escalones para jerarquizar sin recurrir al color, y bordes de 1px como separador por defecto en lugar de sombras. Las sombras existen y son suaves y difusas, pero están reservadas para lo que realmente flota. No hay modo oscuro: `color-scheme: light` está declarado como decisión, no como omisión.

**Key Characteristics:**
- Fondo claro casi blanco (#ffffff) con superficies de descanso en gris papel (#f6f6f7); nada de lienzos de color.
- Un único acento, verde bosque profundo (#145c4a), racionado a la acción principal, el estado seleccionado y los datos verificados.
- El precio total es el elemento tipográfico más pesado de la página (1.25rem / 700 / tabular).
- Íconos de set propio, 20×20, trazo 1.6, siempre en `currentColor`; ninguna fuente de glifos.
- Radios de 6/10/14px más pastillas de 999px para chips y pines; nada de esquinas vivas.
- El estado vive en la URL y la primera carga es del servidor: el esqueleto de carga tiene la forma exacta de las tarjetas, así la página no salta.
- Sin modo oscuro, sin estrellas, sin reseñas, sin señales de urgencia.

## Colors

Una paleta de trabajo: gris neutro frío en trece pasos de rol y un solo acento con temperatura. El color no decora, ordena.

### Primary
- **Verde Bosque Profundo** (`acento`): el único acento del sistema. Vive en el botón Buscar, el chip de filtro activo, el pin de mapa seleccionado, la marca, el `caret-color` de los campos, `::selection`, el `accent-color` del control de rango, el anillo de `:focus-visible`, el monto de descuento y el texto de "Confirmación inmediata".
- **Verde Bosque Oscuro** (`acento-fuerte`): exclusivamente el `:hover` y `:active` de lo que ya es verde. Nunca aparece como color de reposo.
- **Verde Papel** (`acento-tenue`): fondo de la insignia "Confirmación inmediata". Es el único uso de verde como superficie; en la ficha compacta del mapa la misma insignia va sin fondo.

### Neutral
- **Blanco Ficha** (`fondo`): el lienzo de la página, de las tarjetas de barra, del panel de filtros, de los desgloses, de los pines en reposo y de la ficha del mapa.
- **Gris Papel** (`fondo-2`): superficie de descanso y de estado. Fondo del hero de la home, del campo con foco dentro de la barra, de la tarjeta en hover o vinculada al pin, de las píldoras de cuenta, de la caja de detalle en "sin resultados" y de la vía del scrollbar.
- **Gris Placa** (`fondo-3`): solo el hueco que deja una foto que todavía no cargó y el destello del esqueleto. No se usa como fondo de contenido.
- **Gris Línea** (`borde`): el divisor por defecto, 1px: separa la barra fija del contenido, las secciones del diálogo de filtros, las filas del desglose y enmarca el mapa.
- **Gris Trazo** (`borde-fuerte`): el borde de lo que se puede tocar y todavía no está activo —chips, pines, selects, botón secundario, resumen plegado de la barra— más el pulgar del scrollbar y el punteado de los huecos sin foto.
- **Tinta** (`texto`): texto principal, títulos y el fondo invertido de dos controles: el número de página actual y el botón flotante de alternar lista/mapa.
- **Tinta Media** (`texto-2`): texto secundario legible sin esfuerzo —bajadas, ubicación, contexto de la búsqueda, etiquetas del desglose, leyenda "total por N noches".
- **Tinta Tenue** (`texto-3`): apoyos de tercer orden —íconos dentro de los campos, distancia al centro, contadores, extremos del rango, etiquetas de campo en mayúscula, estados inactivos.

### Tertiary
- **Rojo Ladrillo** (`alerta`) sobre **Rosa Papel** (`alerta-tenue`): único par de error, usado en el aviso de validación de la barra de búsqueda (fechas o destino faltantes). No se usa para nada decorativo ni para estados negativos suaves.

### Named Rules
**La regla de un solo verde.** El sistema tiene un acento y ese acento es el verde. Si una pantalla nueva necesita un segundo color para distinguir dos cosas, la respuesta es jerarquía tipográfica o un escalón de gris, no un color nuevo.

**La regla del verde ganado.** El verde marca tres cosas y nada más: la acción principal, el estado seleccionado y el dato verificado (confirmación inmediata, descuento aplicado). No entra en ilustraciones, fondos de sección, franjas ni gráficos.

**La regla de la línea antes que la sombra.** Para separar dos superficies, primero un borde de 1px en `borde`; la sombra recién aparece cuando algo de verdad se despega del plano.

## Typography

**Familia única:** Archivo (Omnibus-Type, Buenos Aires), cargada por `next/font/google` en pesos 400/500/600/700 con `display: swap` y expuesta como `--fuente`. Fallback: `ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`.

**Carácter:** una grotesca de trabajo, de ojo abierto y cifras tabulares parejas: exactamente lo que necesita una página donde la mitad del contenido son números en pesos alineados en columna. No hay fuente de display ni fuente de marca; la jerarquía se hace con peso, tamaño y `letter-spacing` negativo en los tamaños grandes.

### Hierarchy
- **Display** (600, `clamp(1.875rem, 4.4vw, 3rem)`, lh 1.08, ls −0.03em): el titular de la home, limitado a 17ch. Uno por página, y solo en páginas de entrada.
- **Headline** (600, 1.375rem, ls −0.02em): el `h1` de resultados —"N alojamientos en Bariloche"—. Su variante de 1.25rem titula los estados vacíos; 1.125rem, las secciones de la home; 1.0625rem, el encabezado del diálogo de filtros.
- **Title** (600, 1rem, lh 1.3): el título de una tarjeta de resultado. En la ficha compacta del mapa baja a 0.9375rem con lh 1.25 y una sola línea con elipsis.
- **Precio** (700, 1.25rem, ls −0.02em, tabular): el total de la estadía. Es el peso tipográfico más alto de la página. En la ficha del mapa, 1.0625rem; en el pin, 0.8125rem/700 tabular.
- **Body** (400, 0.9375rem, lh 1.5): el texto base del `body` y el valor tipeado dentro de los campos de la barra (ahí sube a 500). Bajadas y párrafos largos se topan en 46–52ch.
- **Body-sm** (400, 0.8125rem): la capa de apoyo —ubicación, distancia, capacidad, filas del desglose, orden, chips (en 500)—. Debajo hay un solo escalón más, 0.75rem, para notas al pie, contadores y leyendas de la galería.
- **Label** (600, 0.6875rem, ls 0.04em, mayúsculas, en `texto-3`): exclusivamente las etiquetas de los campos de la barra de búsqueda (DESTINO, LLEGADA, SALIDA, PERSONAS), donde una mayúscula chiquita sobre el valor es la convención de la categoría.

### Named Rules
**La regla de la cifra tabular.** Todo importe lleva la clase `.cifra` (`font-variant-numeric: tabular-nums`, `font-feature-settings: "tnum" 1`). Los precios se leen en columna y una columna con cifras de ancho variable es una columna que no se puede comparar. Vale también para los contadores de la home y para los precios dentro de los pines del mapa.

**La regla del peso más alto.** En cualquier superficie donde aparezca un precio total, ese número es el elemento tipográfico más pesado del bloque. Nada compite con él: ni el título de la tarjeta, ni el botón.

**La regla de la etiqueta que etiqueta.** La mayúscula chiquita espaciada existe únicamente como `<label>` de un control de formulario. Está prohibido usarla como volanta, antetítulo o categoría decorativa encima de un encabezado.

**La regla del total nombrado.** Un precio nunca aparece solo. Debajo va siempre su leyenda ("total por 3 noches") y al lado su desglose; jamás un "desde $X".

## Layout

**Contenedores.** Tres anchos máximos, cada uno con su trabajo: 1480px para la página de resultados y su barra fija (la lista y el mapa necesitan aire), 1160px para la barra superior de la home, 1000px para el hero y las secciones de contenido de la home. Padding lateral de 1.5rem en escritorio, 1rem por debajo de 1080px.

**Ritmo espacial.** Escala de 4px expresada en rem: 0.25 / 0.375 / 0.5 / 0.625 / 0.75 / 1 / 1.25 / 1.5 / 2 / 3rem. Dentro de una tarjeta se trabaja con 0.25–0.75rem; entre bloques de página, 1.25–1.5rem; entre secciones, 3–4.5rem.

**La página de resultados.** Barra `sticky` arriba (`top: 0`, `z-index: 50`, fondo blanco, borde inferior de 1px) con altura mínima `--barra-alto` (82px): marca a la izquierda, barra de búsqueda en una columna de hasta 720px. Debajo, una grilla de dos columnas: lista en `minmax(0, 1fr)` y mapa en `minmax(360px, 40%)`, separadas por 1.5rem. La lista es a su vez una grilla fluida `repeat(auto-fill, minmax(268px, 1fr))` con gap 1.5rem/1rem, que en escritorio da dos columnas de tarjetas. El título, el aviso de datos de ejemplo y los filtros viven **dentro** de la columna de la lista, no arriba de las dos, para que el mapa arranque a la misma altura que el título.

**El mapa.** `position: sticky` a `calc(var(--barra-alto) + 1.5rem)` y alto `calc(100vh - var(--barra-alto) - 3rem)`, con piso de 420px. Entra entero en el primer pantallazo y no queda nunca bajo el pliegue.

**Puntos de corte reales.**
- **1080px** — el sistema deja de mostrar lista y mapa a la vez: una sola columna, el mapa pasa a `fixed` cubriendo el viewport entre la barra y 4.5rem del pie, y aparece el botón flotante "Ver mapa / Ver lista" centrado abajo. La marca pierde el nombre y queda solo el símbolo.
- **900px** — la barra de búsqueda se reordena a dos columnas (destino y personas a todo el ancho, botón Buscar como fila propia) y la variante compacta arranca **plegada**: se ve un resumen en píldora y al tocarlo se despliega la grilla completa flotando con `sombra-3`.
- **720px** — los chips de filtro dejan de envolver y pasan a un carril horizontal con scroll y barra oculta.
- **560px** — punto menor y único: el paginado esconde las palabras "Anterior/Siguiente" y deja las flechas.

**Densidad y foco.** El `body` arranca en 15px/1.5. `:focus-visible` global: contorno de 2px en el acento con `outline-offset: 2px` y `border-radius: var(--radio-s)`; sobre el botón Buscar verde se invierte a blanco con offset −3px. Hay un enlace "Saltar a los resultados" que vive fuera de pantalla hasta recibir foco.

### Named Rules
**La regla del primer pantallazo.** En resultados, el viajero tiene que ver al mismo tiempo cuántos lugares hay, el precio total del primero y el mapa entero. Cualquier bloque nuevo (banners, promociones, filtros extra) entra **dentro** de la columna de la lista, nunca como franja a todo el ancho por encima.

**La regla de la barra que no se va.** Destino, fechas y personas son editables en todo momento y desde cualquier scroll. Una pantalla que pierde la barra de búsqueda no es de este sistema.

**La regla de una cosa por vez en el teléfono.** Por debajo de 1080px, lista y mapa no comparten pantalla ni compiten: se alternan con un único control flotante.

## Elevation & Depth

El sistema es plano por defecto y se apoya en bordes de 1px y en un escalón de gris para separar superficies. Las tres sombras son suaves, difusas y de dos capas (una de contacto, una ambiental), siempre en la tinta de la marca a baja opacidad (`rgb(23 23 26 / …)`), nunca en negro puro y nunca con desplazamiento duro. Son estructurales, no decorativas: cada nivel dice a qué distancia del plano está el elemento.

### Shadow Vocabulary
- **Contacto** (`--sombra-1`: `0 1px 2px rgb(23 23 26 / 0.06), 0 1px 3px rgb(23 23 26 / 0.05)`): algo apenas levantado y todavía en el flujo. Tarjeta en hover o vinculada al pin, pin de mapa en reposo, flechas de la galería, resumen plegado de la barra, controles nativos del mapa.
- **Flotante** (`--sombra-2`: `0 2px 4px rgb(23 23 26 / 0.05), 0 6px 16px rgb(23 23 26 / 0.09)`): algo que descansa sobre el contenido. Barra de búsqueda del hero, pin activo, aviso dentro del mapa.
- **Superpuesto** (`--sombra-3`: `0 4px 8px rgb(23 23 26 / 0.06), 0 14px 34px rgb(23 23 26 / 0.13)`): algo que tapa. Lista de sugerencias del destino, diálogo de filtros, ficha compacta sobre el mapa, barra desplegada en teléfono, botón flotante de alternar vista.

**Capas.** `z-index` en escalones declarados: sugerencias 30, mapa fijo en teléfono 35, botón de alternar 40, barra desplegada 45, barra fija 50, enlace de salto 100. El velo del diálogo de filtros es `rgb(23 23 26 / 0.42)`.

### Named Rules
**La regla de la sombra que responde.** Ninguna superficie nace con sombra. `--sombra-1` es respuesta a un estado (hover, foco, vínculo con el mapa); `--sombra-2` y `--sombra-3` son propiedad de lo que flota por encima del documento. Una tarjeta en reposo dentro de la grilla es plana.

**La regla de la sombra difusa.** Toda sombra del sistema es blanda y de dos capas. Sombras de desplazamiento duro, contornos negros, dobles bordes tipo sello: fuera del mundo.

## Shapes

Tres radios y una pastilla, sin esquinas vivas en ninguna parte.

- **6px (`--radio-s`)** — controles y superficies chicas: botón Aplicar, botón secundario, selects, números de paginado, insignia de confirmación inmediata, caja de error, foto de la ficha del mapa, anillo de foco, elementos del esqueleto.
- **10px (`--radio`)** — la medida de contenido: marco de la foto de la tarjeta, marco del mapa, panel de sugerencias, caja del desglose, ficha del mapa, avisos y enlaces de destino.
- **14px (`--radio-l`)** — los contenedores grandes: la tarjeta de resultado entera y la barra de búsqueda del hero (la compacta baja a 10px). En la grilla de campos, el primer campo redondea solo su lado izquierdo y el botón Buscar solo el derecho: la barra se lee como una sola pieza.
- **999px** — pastillas: chips de filtro, pines del mapa, contadores, flechas de galería, botón de cerrar, botón flotante de alternar vista, puntos de la galería, pulgar del scrollbar.

**Bordes.** 1px es el único grosor. `borde` para estructura, `borde-fuerte` para lo accionable. El único punteado del sistema es `1px dashed borde-fuerte`, reservado al hueco de una foto que no existe.

**Fotos.** Relación 4:3 con `object-fit: cover` dentro de un marco de 10px con `overflow: hidden`. En hover de la tarjeta, la foto escala a 1.03 en 400ms con `cubic-bezier(0.22, 1, 0.36, 1)`; el marco no se mueve.

### Named Rules
**La regla de los tres radios.** 6 para lo que se toca, 10 para lo que contiene, 14 para lo que agrupa, 999px solo para pastillas. Un radio nuevo es una decisión de sistema, no de componente.

## Components

Carácter general: controles sobrios, de borde fino y fondo blanco, que se calientan con un escalón de gris al hover y se pintan de verde solo cuando están activos. Todas las transiciones usan `--transicion` (`180ms cubic-bezier(0.22, 1, 0.36, 1)`) y solo sobre `background`, `border-color`, `color`, `opacity`, `scale` y `box-shadow`; nunca sobre geometría de layout. `prefers-reduced-motion: reduce` apaga animaciones y transiciones globalmente.

### Buttons
- **Primario (Buscar):** verde acento sobre blanco puro, peso 600, sin borde, esquina derecha de la barra (`0 14px 14px 0`), padding `0 1.25rem` y un ícono de lupa a 0.5rem del texto. Hover: `acento-fuerte`. Foco: contorno blanco con offset −3px, por dentro del botón.
- **Primario de diálogo (Aplicar):** mismo verde, radio 6px, padding `0.5625rem 1.125rem`.
- **Secundario ("Sumá tu alojamiento"):** fondo blanco, borde `borde-fuerte` de 1px, radio 6px, 0.875rem/600; hover con fondo `fondo-2`.
- **Invertido (alternar lista/mapa):** pastilla en tinta sólida sobre texto blanco, fija abajo y centrada, con `sombra-3`. Solo existe por debajo de 1080px y solo para cambiar de vista.
- **De texto (Limpiar filtros):** sin caja, `texto-2`, subrayado con `text-underline-offset: 3px`.
- **Icónicos (cerrar, flechas de galería):** círculo de 26–32px, `place-items: center`, sin texto, con el ícono del set propio a `currentColor`.

### Chips
- **Reposo:** pastilla blanca con borde `borde-fuerte`, 0.8125rem/500, padding `0.375rem 0.75rem`, ícono opcional de 15px a la izquierda.
- **Hover:** borde a `texto-3`, fondo `fondo-2`.
- **Activo:** relleno verde acento, borde del mismo verde, texto blanco; el contador que llevan adentro se vuelve una pastilla de blanco al 22%.
- **Comportamiento:** los chips abren el diálogo de filtros o togglean un filtro directo. Por debajo de 720px no envuelven: scrollean en horizontal con la barra oculta.

### Cards / Containers
La tarjeta de resultado es la unidad de contenido del sistema.
- **Forma:** radio 14px, padding 0.5rem, sin borde y sin fondo en reposo.
- **Estado:** en hover, foco de teclado o vínculo con el pin del mapa toma `fondo-2` + `sombra-1`, la foto escala 1.03 y el título se subraya.
- **Contenido, en este orden:** galería 4:3 → título → insignia "Confirmación inmediata" → subtipo · localidad · provincia → distancia al centro → unidad y capacidad con ícono de personas (+N unidades más) → hasta cinco íconos de comodidad → bloque de precio.
- **Enlace de área completa:** un solo `<a>` en el título con `::after` absoluto cubriendo la tarjeta; los controles que tienen que seguir siendo clickeables (desglose, flechas de galería) suben de capa con `z-index`. Nunca se anidan interactivos.
- **Desglose:** `<details>` con summary subrayado en `borde-fuerte`; abierto muestra un `<dl>` de mínimo 260px con borde de 1px, una fila por concepto, el total separado por una línea superior, y una nota de cierre que dice si hay o no cargo de servicio.

### Inputs / Fields
- **Barra de búsqueda:** grilla de campos separados por gaps de 1px sobre fondo `borde`, de modo que las líneas divisorias son el propio contenedor. Cada campo: etiqueta en mayúscula chiquita arriba, valor en 0.9375rem/500 abajo, input sin borde ni fondo propio y con `outline: none` (el foco lo marca el campo entero cambiando a `fondo-2`).
- **Autocompletado de destino:** panel a `calc(100% + 6px)`, radio 10px, `sombra-3`, máximo 340px de alto; cada opción es una grilla de ícono 18px / nombre + provincia / contador en pastilla, con la opción resaltada en `fondo-2`.
- **Error de validación:** caja `alerta-tenue` con texto `alerta` de 0.8125rem/500, radio 6px, debajo de la barra.
- **Select de orden y rango de precio:** select con borde `borde-fuerte` y radio 6px; el `input[type=range]` usa `accent-color: var(--acento)`.

### Navigation
No hay menú: la navegación es la búsqueda. La barra superior de resultados lleva marca a la izquierda y buscador a la derecha; la de la home, marca y un único enlace secundario. La marca es un símbolo SVG de 26px de trazo 1.9 en verde acento más el nombre en 1rem/700 con ls −0.02em; por debajo de 1080px el nombre desaparece y queda el símbolo.

**El nombre público no está decidido.** Vive aislado en la constante `NOMBRE` de `frontend/src/componentes/Marca.tsx` ("Suite Cabaña" es nombre de trabajo). Cambiar la marca es cambiar ese archivo y nada más: ninguna otra superficie puede hardcodear el nombre.

### Íconos
Set propio en `frontend/src/componentes/Iconos.tsx`: 24 íconos SVG de 20×20, `fill: none`, trazo 1.6 con extremos y uniones redondeados, todo en `currentColor` y `aria-hidden` salvo que reciban título. Se dibujan a 20px por defecto, a 18px dentro de campos y listas, a 15px en la fila de comodidades y a 13–14px en insignias. Las comodidades se mapean por código de catálogo (`ICONOS_COMODIDAD`) y **un código sin ícono no dibuja nada**: no hay ícono genérico de relleno.

### Vínculo tarjeta ↔ mapa (componente firma)
La interacción propia del sistema, y la única que no es puro estándar.
- **Escritorio:** pasar el mouse o tabular sobre una tarjeta activa su pin (relleno verde, `scale: 1.1`, `z-index: 5`, `sombra-2`); pasar sobre un pin resalta la tarjeta (`fondo-2` + `sombra-1`); hacer clic en el pin lleva la lista hasta la ficha con `scrollIntoView({ behavior: "smooth", block: "center" })`.
- **Teléfono (vista mapa):** el hover no existe; tocar un pin lo selecciona y abre **FichaMapa**, una tarjeta horizontal anclada al pie del mapa (foto de 108×92 a la izquierda, título de una línea, detalle, confirmación inmediata, precio de 1.0625rem/700) con `sombra-3` y un botón de cerrar circular de 26px.
- **Pines:** pastilla blanca con borde `borde-fuerte` que muestra el precio total formateado en pesos, tabular; hover `scale: 1.06`.

### Estados con nombre propio
- **Cargando** (`loading.tsx`): esqueleto con la forma exacta de la grilla real —seis tarjetas, foto 4:3, dos líneas y una barra de precio— con un barrido diagonal de `fondo-2` → `fondo-3` → `fondo-2` a 1.4s. Lleva `aria-busy`, `aria-live="polite"` y un texto solo para lectores. La página no salta cuando llegan los datos.
- **Sin resultados / sin fechas / destino desconocido / error:** caja centrada de 560px con un círculo gris de 46px, título de 1.25rem, cuerpo topado en 46ch, una caja de detalle en `fondo-2` y, cuando hay, una lista de destinos sugeridos con la misma fila de ícono/nombre/contador que la home.
- **Aviso de datos de ejemplo** (`AvisoDemo`): presente en todos los estados de `/buscar` y en la home. La interfaz declara que los alojamientos, precios y contadores son de prueba, que las localidades son reales y que las fotos son de Wikimedia Commons con licencia libre. Es contenido obligatorio mientras no haya oferta real.

### Named Rules
**La regla del vínculo.** Toda superficie que muestre a la vez una lista y un mapa mantiene el resaltado bidireccional y accesible por teclado (`onFocus`/`onBlur`, no solo `onMouseEnter`).

**La regla del estado con nombre.** Ningún estado se resuelve con un spinner genérico ni con una frase muerta. Carga = esqueleto con la forma del contenido. Vacío = motivo explícito, más una salida (sugerencias, cambiar fechas).

**La regla del dato provisorio declarado.** Mientras los datos sean de semilla, la pantalla lo dice en su propia superficie. Un alojamiento de ejemplo no puede pasar por real ni por un descuido. Las fotos provisorias llevan procedencia y crédito en `frontend/public/fotos/demo/creditos.json`.

## Do's and Don'ts

### Do:
- **Do** usar las variables de `frontend/src/app/globals.css` para todo color, radio, sombra y transición. Un valor literal en un módulo CSS es deuda, no una decisión.
- **Do** poner `.cifra` en todo importe, contador y precio de pin.
- **Do** dejar el total de la estadía como el número más pesado del bloque, con su leyenda "total por N noches" y su desglose accesible en el mismo lugar.
- **Do** formatear plata con `pesos()` / `pesosExactos()` de `frontend/src/lib/formato.ts` (Intl es-AR, ARS) y fechas con `diaMes` / `diaMesAnio` / `rangoFechas`. Los importes llegan de la API como string para no perder precisión y solo se muestran; nunca se hace aritmética de dinero en el cliente.
- **Do** escribir la copia en español rioplatense con voseo ("Encontrá dónde quedarte", "Sumá tu alojamiento").
- **Do** usar los íconos de `Iconos.tsx` a 20/18/15px con `currentColor`. Si falta uno, se dibuja en ese archivo con trazo 1.6 sobre caja de 20.
- **Do** mantener `:focus-visible` visible en todo control y el enlace de salto al contenido; el piso es navegación por teclado completa.
- **Do** dar a cada estado (carga, vacío, error) una forma propia con la silueta del contenido real.
- **Do** declarar como datos de ejemplo todo contenido de semilla, en la misma pantalla donde se muestra.
- **Do** aislar el nombre de marca en `Marca.tsx`.

### Don't:
- **Don't** mostrar estrellas, puntajes, reseñas ni "N personas están viendo esto": no hay reseñas en el producto y la urgencia falsa está rechazada por el contrato de dirección. Donde la categoría pone estrellas va "Confirmación inmediata", que es verificable.
- **Don't** mostrar "desde $X", precios por noche como cifra principal ni totales sin desglose. El precio que se ve es el total real de esas fechas.
- **Don't** agregar un segundo acento cromático, degradados de color, franjas de color ni fondos ilustrados. El único verde es `acento`.
- **Don't** construir un modo oscuro ni suponer uno: `color-scheme: light` es una decisión tomada. Una pantalla nueva no inventa la contraparte oscura por su cuenta.
- **Don't** escribir colores, radios ni sombras en hexadecimal o px dentro de un módulo CSS.
- **Don't** usar la etiqueta en mayúscula espaciada como volanta, antetítulo o categoría decorativa. Es solo `<label>` de un campo.
- **Don't** usar íconos de fuentes de glifos, emojis como íconos ni paquetes externos de íconos: el set propio es el único.
- **Don't** meter sombras de desplazamiento duro, contornos negros ni bordes de más de 1px.
- **Don't** poner una franja a todo el ancho por encima de la lista en `/buscar`: empuja el mapa bajo el pliegue y rompe el primer pantallazo.
- **Don't** anidar controles interactivos dentro del área del enlace de la tarjeta sin subirlos de capa.
- **Don't** inventar nombres de alojamientos, cantidades de propiedades, sponsors, métricas de cobertura ni precios presentados como vigentes.
- **Don't** animar geometría de layout ni ignorar `prefers-reduced-motion`.
