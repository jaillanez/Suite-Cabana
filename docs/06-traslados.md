# Traslados

**Documento 06 · Especificación de producto (PRD)**
Versión 0.1 · Noviembre 2026 · Depende de: `00-vision-general.md`, `02-fase2-beneficios-servicios.md` (parte B).

---

## 1. Objetivo

Que un prestador publique sus traslados (aeropuerto y terminal, entre localidades,
dentro de la ciudad) con sus vehículos y precios, y que el viajero reserve un
vehículo para un día, una hora, un origen y un destino, con el mismo circuito de
pago que un alojamiento.

## 2. Decisiones tomadas

| Tema | Decisión |
|---|---|
| Qué se reserva | **Un vehículo entero** (traslado privado) para un viaje: día y hora, origen, destino, pasajeros y valijas |
| Cómo se cobra | Lo elige **cada prestador**, por vehículo: **tramos fijos** (por vehículo o por persona) y/o **por kilómetro** |
| Distancia por kilómetro | Línea recta entre los dos puntos por un **factor de ruta** del prestador (por defecto 1,3). Todavía no hay proveedor de rutas; cuando lo haya, cambia solo este cálculo |
| Disponibilidad | El vehículo queda ocupado por el viaje, la vuelta a la base (si el prestador lo indica) y la preparación. La misma restricción de exclusión que los salones: dos viajes no se pisan |
| Anticipación | Una mínima que elige el prestador (por defecto 12 h) y hasta **12 meses** |
| Requisitos al prestador | La plataforma no pide habilitaciones ni seguros (Dirección, noviembre 2026) |

## 3. Lo que decide cada prestador

| Parámetro | Dónde | Por defecto |
|---|---|---|
| Pasajeros y valijas | Por vehículo (`unidad.capacidad`, `unidad.equipaje`) | Valijas sin límite |
| Lugares de origen y destino | Por publicación (`lugar_traslado`): "Aeropuerto de San Juan", "Centro"… con su punto en el mapa | — |
| Tramos fijos | Por vehículo (`tramo_traslado`): origen, destino, duración, precio por vehículo o por persona, si vale en los dos sentidos | — |
| Tarifa por km | Por vehículo (`tarifa_traslado`): bajada, precio por km, mínimo, radio de servicio desde la base, factor de ruta, velocidad media | Sin tarifa por km |
| Recargo nocturno | Por vehículo: desde, hasta y porcentaje | Sin recargo |
| Vuelve a la base | Por vehículo: si después del viaje el vehículo queda ocupado lo que tarda en volver | Sí |
| Preparación entre viajes | Por vehículo (`unidad.preparacion_minutos`) | 0 |
| Anticipación mínima | Por vehículo, en horas | 12 h |
| Política de cancelación, seña | Por publicación, como las excursiones (plantilla o tramos propios) | — |

## 4. Modelo

```
Publicacion ──< LugarTraslado            (puntos con nombre; uno puede ser la base)
     └──< Unidad (vehículo) ──< TramoTraslado   (origen → destino, precio)
                   └── TarifaTraslado           (por km y reglas del vehículo)
                   └──< BloqueoHorario          (viajes, retenciones, bloqueos a mano)
```

- La **cotización** es una cuenta pura (`precios_traslado`): el tramo o los
  kilómetros, el recargo nocturno, y hasta cuándo queda ocupado el vehículo.
- La **ocupación** reutiliza `bloqueo_horario`: un viaje bloquea desde la salida
  hasta el fin de la vuelta y la preparación.

## 5. Etapas

Cada etapa se puede publicar por separado. Hechas (noviembre 2026): las cuatro.

| Etapa | Contenido |
|---|---|
| 1. Base | Subtipos; vehículos con pasajeros y valijas; lugares, tramos y tarifa por km; recargo nocturno; cotización pura; ocupación del vehículo sin superposición |
| 2. Reserva | Cotizar y reservar con retención; datos del viaje (vuelo, dirección exacta); ida y vuelta como dos ítems de una misma reserva; cancelación y comisión |
| 3. Alta y edición | "Traslado" al publicar; editor de vehículos, lugares, tramos, tarifa y reglas; agenda de cada vehículo |
| 4. Búsqueda y ficha | Buscar por origen, destino, día y pasajeros; ficha y reserva web; "¿Te buscamos en el aeropuerto?" desde la reserva de un alojamiento |

Cómo quedó la etapa 1 (`app/services/precios_traslado.py`, `app/services/traslados.py`,
migración 0016): solo backend.

Cómo quedó la etapa 2 (`app/services/reservas_traslado.py`, `app/api/v1/traslados.py`,
migración 0017): solo backend y API.

- Cada extremo es un **lugar** del prestador o un **punto del mapa con su dirección**
  (obligatoria). De lugar a lugar con tramo cargado se cobra el tramo; si no, por km.
- **Ida y vuelta**: dos ítems de la misma reserva, cada uno con su precio, su
  recargo nocturno, su comisión y su retención. Se confirman, se cancelan y se
  caen juntos: si la vuelta no tiene lugar, no se reserva la ida.
- Si la vuelta sale antes de que el vehículo alcance a volver a la base, el chofer
  **espera**: la ocupación de la ida termina donde empieza la vuelta.
- La vuelta tiene que salir después de que llega la ida.
- **Datos del viaje** (`item_reserva.datos_servicio`): vuelo de ida y de vuelta,
  direcciones y notas. El viajero corrige el vuelo y las notas de los viajes que
  no salieron (`PATCH /traslados/reservas/{codigo}/viaje`); las direcciones no,
  porque el precio por km salió de ese punto. El prestador los ve recién con la
  reserva pagada (o esperando su respuesta).
- Política de cancelación: la de la publicación (plantilla o tramos propios), en
  días, como las excursiones.
- Los bloqueos de horario de un vehículo van de 5 minutos a 120 horas (un salón
  sigue entre 30 minutos y 48 horas).

Cómo quedó la etapa 3 (`app/api/v1/mis_traslados.py`, `UnidadesTraslado.tsx`):

- "Traslados" al crear una publicación, con sus tres subtipos y comodidades
  propias (cartel de bienvenida, espera si el vuelo se demora, silla para bebé,
  mascota, factura).
- **Lugares** de la publicación: nombre y punto en el mapa; uno puede ser la base
  (solo uno). Quitar un lugar quita los tramos que salen o llegan ahí; volver a
  cargar el mismo nombre lo reactiva. Hasta 40.
- **Vehículos**: pasajeros (hasta 80), valijas, minutos entre viajes. Cada uno con
  sus **recorridos de precio fijo** (hasta 60; uno por sentido, por vehículo o
  por persona, si vale a la vuelta) y sus **reglas** (precio por km, bajada,
  mínimo, radio, factor de ruta, velocidad, recargo nocturno, vuelta a la base,
  anticipación), que se guardan todas juntas.
- Para mandarla a revisión, cada vehículo necesita un recorrido fijo entre dos
  lugares activos o un precio por km.
- La **agenda** de cada vehículo es la de los salones: viajes, pagos en curso y
  bloqueos a mano.
- La política de cancelación es la plantilla o tramos propios, como las
  excursiones.

Cómo quedó la etapa 4 (`app/services/traslados_viajero.py`, `/traslados`,
`/traslado/[slug]`, `ReservaTraslado.tsx`, `ViajeReserva.tsx`):

- **Búsqueda** por destino, pasajeros, valijas y un lugar ("aeropuerto", "terminal":
  busca en los nombres de los lugares de cada prestador). **No filtra por día**:
  cuánto ocupa un viaje al vehículo depende del recorrido, así que si está libre
  se responde en la ficha, con el viaje armado. Es un cambio sobre lo previsto en
  §5 ("buscar por día").
- **Ficha**: vehículos, recorridos de precio fijo, tarifa por km, recargo y
  anticipación. De los lugares se muestra solo el nombre: el punto de la base
  puede ser la casa del prestador.
- **Opciones** (`POST /traslados/opciones`): con el viaje armado —lugar o
  dirección en el mapa, día y hora, pasajeros, valijas, vuelta—, cada vehículo
  con su precio y si está libre, o por qué no (no entran, no hace ese recorrido,
  ya tiene un viaje). Sale de la misma cuenta que la reserva.
- **Detalle de la reserva**: ida y vuelta, direcciones, vuelo y notas; el viajero
  corrige el vuelo y las notas. El prestador ve los viajes en su lista de
  reservas y los datos del viaje recién con la reserva pagada.
- **Venta cruzada**: la ficha de un alojamiento muestra los traslados de la
  localidad ("Cómo llegar"), y la reserva de una estadía ofrece "¿Te buscamos en
  el aeropuerto?" con el día de llegada y las personas ya cargados.

## 6. Fuera de alcance por ahora

- **Traslados compartidos con horario fijo** (un shuttle que sale a las 9 con
  lugares sueltos). Se parecen más a una excursión por turno y cupo que a un
  vehículo entero; se definen cuando haya un prestador que los ofrezca.
- **Chofer por hora** (a disposición todo el día).
- Distancia por calle real: espera a un proveedor de rutas.

## 7. Preguntas abiertas

| Pregunta | Responsable | Bloqueante |
|---|---|---|
| ¿Hace falta ofrecer traslados compartidos con horario fijo? | Dirección | No |
| ¿Se contrata un proveedor de rutas para la distancia por calle? | Dirección / Técnica | No |
| El vehículo se ocupa desde la salida del viaje: no se cuenta lo que tarda en llegar desde la base hasta el origen. Hoy el prestador lo cubre con la preparación. ¿Se calcula el acercamiento con la base y los puntos? | Técnica | No |
