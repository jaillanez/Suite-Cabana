# Excursiones y actividades

**Documento 05 · Especificación de producto (PRD)**
Versión 0.1 · Noviembre 2026 · Depende de: `00-vision-general.md`, `02-fase2-beneficios-servicios.md` (parte B).

---

## 1. Objetivo

Que un prestador publique una excursión o actividad (cabalgata, trekking, visita a
bodega) con sus turnos y su cupo, y que el viajero reserve lugares para una salida
concreta con el mismo circuito de pago que un alojamiento.

## 2. Decisiones tomadas

| Tema | Decisión |
|---|---|
| Cómo se reserva | Por **turno y cupo**: el viajero elige una salida (día y hora) y cuántas personas van |
| Turnos | Se repiten por día de la semana ("martes y jueves a las 9"), con temporada opcional |
| Excepciones | El prestador **suspende** una salida, le **cambia el cupo** o agrega una **salida especial** fuera de los turnos |
| Anticipación | Hasta **12 meses**, como las cabañas |
| Requisitos al prestador | La plataforma no pide habilitaciones ni seguros (Dirección, noviembre 2026) |

## 3. Modelo

```
Unidad ──< TurnoExcursion            (la regla que se repite)
   └────< SalidaExcursion ──< CupoTomado
               └── turno (nulo en una salida especial)
```

- **Unidad**: la actividad que se reserva ("Cabalgata al dique").
- **TurnoExcursion**: días de la semana, hora de salida, duración, cupo y temporada.
- **SalidaExcursion**: una salida de un día. No se guarda una por cada martes del
  año: se calcula del turno, y la fila se crea recién cuando hay algo que guardar
  de ese día (alguien toma lugar, el prestador la suspende o le cambia el cupo).
  Desde ahí tiene su propia hora y su propio cupo: **si el prestador cambia el
  turno, lo ya vendido no se mueve.**
- **CupoTomado**: los lugares que ocupa una retención mientras se paga, una
  reserva o una venta que el prestador hizo por fuera.

### Cero sobreventa

Como con las noches (CLAUDE.md §6), lo garantiza la base:

- `ocupados` no puede pasar de `cupo` por una restricción (`cupo_no_se_pasa`).
- Se suma con un UPDATE sobre la fila de la salida, bloqueada mientras dura la
  transacción. Si dos viajeros piden los últimos lugares a la vez, el segundo
  espera al primero y ve lo que quedó.
- Una retención vencida que la tarea todavía no soltó se muestra libre, y quien
  pide lugares la suelta antes de tomarlos. La tarea periódica suelta el resto.

## 4. Etapas

Cada etapa se puede publicar por separado. Hecha (noviembre 2026): **1**.

| Etapa | Contenido |
|---|---|
| 1. Base | Subtipos; turnos que se repiten; salidas con suspensión, cambio de cupo y salidas especiales; cupo sin sobreventa; retenciones con vencimiento. Tests de concurrencia con dos conexiones |
| 2. Precio y reserva | Precio por tipo de pasajero; cotización y reserva con retención; mínimo de participantes con cancelación automática; política de cancelación; comisión |
| 3. Alta y edición | "Excursión" al publicar; editor de turnos, salidas y precios; panel del prestador con las salidas y los anotados |
| 4. Búsqueda y ficha | Sección Excursiones, búsqueda por fecha y personas, ficha con calendario de salidas, reserva desde la web |

Cómo quedó la etapa 1:
- Backend solamente (`app/services/salidas.py`, migración 0014). Un prestador
  todavía no puede publicar una excursión: el alta acepta solo alojamiento y salón.
- Por ahora no se suspende una salida con gente anotada: hace falta el reintegro
  de la etapa 2.

## 5. Preguntas abiertas

| Pregunta | Responsable | Bloqueante |
|---|---|---|
| Política de cancelación de las excursiones (plazos y porcentajes) | Dirección | Etapa 2 |
| Mínimo de participantes: con cuánta anticipación se cancela la salida si no se llega | Dirección | Etapa 2 |
| Si el prestador suspende una salida con gente anotada (lluvia), ¿se devuelve el 100 %? | Dirección | Etapa 2 |
| Edades de "menor" y quién cuenta como jubilado para el precio | Dirección | Etapa 2 |
