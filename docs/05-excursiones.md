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
| Reglas del servicio | Las decide **cada prestador**, no la plataforma (Dirección, noviembre 2026). Ver §3 |

## 3. Lo que decide cada prestador

La plataforma solo pone valores por defecto; cada uno los cambia en su publicación.

| Parámetro | Dónde | Por defecto |
|---|---|---|
| Política de cancelación | Una plantilla del operador, o tramos propios (`publicacion.tramos_cancelacion`: días antes y porcentaje, hasta 5) | Sin política: sin reintegro |
| Reintegro si la salida no va (suspensión o falta de mínimo) | `publicacion.reintegro_si_no_sale`, de 0 a 100 % de lo pagado | 100 % |
| Mínimo de personas | Por turno (`minimo_personas`), de 1 al cupo | 1 (sin mínimo) |
| Cuándo se decide por el mínimo | Por turno (`aviso_minimo_horas`), de 0 a 720 h antes | 24 h |
| Tipos de pasajero | Por actividad (`precio_pasajero`): nombre, descripción, edades, precio, si ocupa lugar | Ninguno: sin precios no se reserva |

Lo que cada reserva aceptó queda copiado en ella: el turno se copia en la salida
(mínimo y aviso) y la política en la reserva (tramos y reintegro si no sale).
Cambiar un parámetro después no cambia lo ya reservado.

## 4. Modelo

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
- **PrecioPasajero**: un precio por tipo de pasajero ("Adulto", "Menor de 3 a 12",
  "Jubilado", "Bebé en brazos" sin cupo). Las edades son informativas.

### Cero sobreventa

Como con las noches (CLAUDE.md §6), lo garantiza la base:

- `ocupados` no puede pasar de `cupo` por una restricción (`cupo_no_se_pasa`).
- Se suma con un UPDATE sobre la fila de la salida, bloqueada mientras dura la
  transacción. Si dos viajeros piden los últimos lugares a la vez, el segundo
  espera al primero y ve lo que quedó.
- Una retención vencida que la tarea todavía no soltó se muestra libre, y quien
  pide lugares la suelta antes de tomarlos. La tarea periódica suelta el resto.

## 5. Etapas

Cada etapa se puede publicar por separado. Hechas (noviembre 2026): **1** y **2** (solo backend).

| Etapa | Contenido |
|---|---|
| 1. Base | Subtipos; turnos que se repiten; salidas con suspensión, cambio de cupo y salidas especiales; cupo sin sobreventa; retenciones con vencimiento. Tests de concurrencia con dos conexiones |
| 2. Precio y reserva | Precio por tipo de pasajero; cotización y reserva con retención; mínimo de participantes con cancelación automática; política de cancelación; comisión |
| 3. Alta y edición | "Excursión" al publicar; editor de turnos, salidas y precios; panel del prestador con las salidas y los anotados |
| 4. Búsqueda y ficha | Sección Excursiones, búsqueda por fecha y personas, ficha con calendario de salidas, reserva desde la web |

Cómo quedó la etapa 1 (`app/services/salidas.py`, migración 0014): turnos,
salidas, excepciones y cupo sin sobreventa.

Cómo quedó la etapa 2 (`app/services/reservas_excursion.py`, `/api/v1/excursiones`,
migración 0015):
- Cotización y reserva de lugares en una salida, con el mismo circuito de pago,
  comisión y aviso que una estadía. Se retienen los lugares de quienes ocupan cupo.
- Un pago que llega con la retención ya vencida vuelve a pedir los lugares; si no
  hay, la reserva se cancela y el pago queda para devolver.
- **Si la salida no va** (`no_sale`): se cancelan sus reservas con el reintegro que
  eligió el prestador, se sueltan los lugares que anotó por fuera y la salida queda
  suspendida.
- **Mínimo de personas**: la tarea periódica, a la hora de decidir, confirma la
  salida (llegó al mínimo) o la cancela. Cuentan las reservas pagadas y lo que
  anotó el prestador; quien está pagando, no. Una salida confirmada va aunque
  después alguien cancele. Pasada la hora, una salida sin confirmar ya no se vende.
- Todavía no hay pantallas: un prestador no puede publicar una excursión ni
  cargar estos parámetros (etapa 3), y el viajero no la ve en la web (etapa 4).

## 6. Preguntas abiertas

Ninguna por ahora: las reglas del servicio son parámetros de cada prestador (§3).
