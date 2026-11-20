---
version: 1
slug: "frontend-src-app-alojamiento-slug-page-tsx"
primary_target: "frontend/src/app/alojamiento/[slug]/page.tsx"
related_targets: []
---

# Ficha de alojamiento — `/alojamiento/[slug]`

**Modo:** Operate. Última pantalla antes de decidir.

**Audiencia y trabajo:** el viajero que ya eligió dos o tres candidatos y viene a descartar o confirmar uno. Llega con fechas desde `/buscar`, o sin fechas desde Google.

**Acción primaria:** elegir una unidad concreta y avanzar a reservar. Mientras la reserva no exista (Bloque 6), la acción queda visible y explicada, nunca falsamente operativa.

**Prueba disponible:** fotos, descripción, ubicación en mapa, servicios, reglas de la casa, unidades con capacidad, precio total desglosado por unidad para las fechas elegidas, política de cancelación, y quién es el prestador. Sin reseñas: no existen.

**Restricciones:** todo sale de `GET /api/v1/publicaciones/{slug}`. Sin fechas no se muestra precio total, solo la tarifa base por noche, nombrada como tal.

## Direction contract

**THESIS:** La ficha que no esconde nada. Cada unidad muestra si entra, si está libre y cuánto sale en total para esas fechas — y cuando no se puede, dice por qué con palabras. Rechaza la ficha de un solo precio grande que se descompone recién en el checkout, y rechaza el "consultar disponibilidad" que no responde nada.

**OWN-WORLD:** El sistema ya documentado en DESIGN.md: fondo claro, un solo acento verde reservado a la acción, Archivo con cifras tabulares en todo importe, tres radios, sombras difusas, línea antes que sombra. Nada nuevo.

**STORY:** El viajero ve el lugar, entiende dónde queda y qué incluye, elige entre las unidades la que le sirve, ve el total exacto con su desglose, y sabe qué pasa si cancela.

**FIRST VIEWPORT:** Título, tipo, distrito y departamento arriba. Debajo, la galería a ancho completo con la foto principal grande y el resto en mosaico. Inmediatamente después, en dos columnas: a la izquierda descripción, servicios y reglas; a la derecha, fija al scrollear, la tarjeta de fechas con las unidades y el total de la seleccionada.

**FORM:** El estándar de la categoría, la misma decisión registrada en PRODUCT.md. Superficie derivada de un mundo ya establecido: sin torneo de concepto, con la composición que la categoría ya resolvió y el equipo eligió.

**FINISH:** unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance.
