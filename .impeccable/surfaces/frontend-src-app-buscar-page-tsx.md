---
version: 1
slug: "frontend-src-app-buscar-page-tsx"
primary_target: "frontend/src/app/buscar/page.tsx"
related_targets: []
---

# Búsqueda de alojamientos — `/buscar`

**Modo:** Operate. El viajero llega con destino, fechas y personas ya elegidos y viene a descartar rápido hasta quedarse con dos o tres fichas.

**Audiencia y trabajo:** viajero argentino comparando de noche, en el teléfono, con fechas rígidas por un feriado y presupuesto en pesos. Llega desde el buscador de la home o desde una búsqueda en Google a una página de destino.

**Acción primaria:** abrir la ficha de una unidad concreta con esas fechas cargadas.

**Prueba disponible:** disponibilidad real verificada contra bloqueos y calendarios externos; precio total calculado por el backend para esas fechas y esas personas; nombre del prestador. No hay reseñas ni calificaciones: no se inventan.

**Restricciones:** todos los datos salen de la base por `GET /api/v1/publicaciones/buscar`. Fotos provisorias de Wikimedia Commons con crédito. Mapa MapLibre + OpenStreetMap con atribución. Todo el estado en la URL, primera carga en el servidor por SEO.

**Decisiones abiertas que el build no inventa:** quién paga la comisión (se lee de la regla vigente y el desglose siempre la nombra); porcentajes de las políticas de cancelación (no se muestran acá).

## Direction contract

**THESIS:** La página de resultados de un marketplace de alojamientos, ejecutada como la ejecutan los que mandan, y ganando en el único lugar donde se puede ganar: el precio que se ve es el total real de esas fechas, con su desglose a la vista, y la disponibilidad está verificada. Rechaza inventar un mundo visual propio donde el viajero necesita reconocer el patrón en un segundo; rechaza también el "desde $X" y cualquier señal de urgencia falsa.

**OWN-WORLD:** El estándar de la categoría, elegido explícitamente por el equipo (registrado en PRODUCT.md) con la vara puesta en Airbnb, Booking y Despegar. Ground claro, tarjeta como unidad de contenido con la foto dominante, barra de búsqueda persistente, filtros en línea, mapa en columna fija. Sin ironía, sin guiños, sin un detalle raro metido para tener personalidad. La identidad vive en la precisión: números tabulares en los precios, desglose legible, estados con nombre propio.

**STORY:** El viajero entiende en el primer pantallazo cuántos lugares hay para sus fechas, cuánto cuesta cada uno en total, y a qué distancia está del centro. Cree que el precio no va a cambiar porque lo ve desglosado antes de entrar. Hace clic en la ficha que le cierra.

**FIRST VIEWPORT:** Arriba, la barra de búsqueda con destino, llegada, salida y personas siempre editables, que no se va al hacer scroll. Debajo, una línea que dice cuántos alojamientos hay para esas fechas y el orden aplicado, con los filtros a su derecha. A la izquierda, la lista en dos columnas en escritorio: foto a sangre arriba de cada tarjeta, título, tipo y localidad, distancia al centro, capacidad, y el bloque de precio con el total en el peso más alto de la página y el "total, N noches" debajo. Donde Airbnb pone las estrellas va "Confirmación inmediata", que es un dato verdadero. A la derecha, el mapa ocupando el 40% del ancho, fijo, con los precios en los pines. En teléfono, una columna y un botón que alterna a mapa completo.

**FORM:** El estándar de la categoría — la salida permanente de la ronda de dirección, tomada explícitamente por el equipo por sobre las tres direcciones propuestas y la alternativa competitiva. Seed key 11e0dd6c, modo operate.

**FINISH:** unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance.
