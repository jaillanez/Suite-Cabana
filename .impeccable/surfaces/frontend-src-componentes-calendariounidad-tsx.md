---
version: 1
slug: "frontend-src-componentes-calendariounidad-tsx"
primary_target: "frontend/src/componentes/CalendarioUnidad.tsx"
related_targets: []
---

# Calendario de la unidad — sección de `/mis-publicaciones/[id]`

**Modo:** Operate. Sección dentro de una superficie ya establecida: hereda el editor, no inventa mundo.

**Audiencia y trabajo:** el prestador que ya publica en Booking y Airbnb y necesita que los tres calendarios digan lo mismo. Y el mismo prestador guardándose unas noches para uso propio.

**Acción primaria:** conectar el calendario de la otra plataforma, y bloquear fechas a mano.

**Prueba disponible:** los tramos reales que tiene tomada la unidad, con su origen; la última sincronización de cada calendario externo y el motivo si falló.

**Restricciones:** la segunda fecha es el día de salida y esa noche queda libre — se dice en la pantalla, no se asume. Solo los bloqueos manuales se sueltan desde acá; los de reservas y calendarios los maneja su fuente. El calendario que se exporta no publica quién reservó ni cuánto pagó.

## Direction contract

**THESIS:** Un solo lugar donde se ve todo lo que tiene tomada la unidad, venga de donde venga, y se dice de dónde viene cada cosa. Rechaza el calendario que muestra "ocupado" sin decir por qué, que es el que obliga a abrir tres pestañas para entender una fecha.

**OWN-WORLD:** El sistema documentado en DESIGN.md. El origen de cada tramo se distingue con un punto de color, el mismo recurso que ya usan los estados de publicación; nunca con una franja lateral.

**STORY:** El prestador abre el calendario de una unidad, ve sus fechas propias y las que trajo cada plataforma, se guarda unas noches, pega la dirección del calendario de Booking, sincroniza, y copia la suya para pegarla allá.

**FIRST VIEWPORT:** Las fechas tomadas primero, en lista, cada una con su rango, su origen y su motivo. Debajo el formulario de bloqueo con la aclaración de que la salida es exclusiva. Después los calendarios externos con su estado, y último la dirección propia para copiar.

**FORM:** El estándar de la categoría, la decisión registrada en PRODUCT.md. Sección dentro de una superficie establecida: hereda.

**FINISH:** unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance.
