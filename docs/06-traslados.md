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

Cada etapa se puede publicar por separado. Hecha (noviembre 2026): **1**.

| Etapa | Contenido |
|---|---|
| 1. Base | Subtipos; vehículos con pasajeros y valijas; lugares, tramos y tarifa por km; recargo nocturno; cotización pura; ocupación del vehículo sin superposición |
| 2. Reserva | Cotizar y reservar con retención; datos del viaje (vuelo, dirección exacta); ida y vuelta como dos ítems de una misma reserva; cancelación y comisión |
| 3. Alta y edición | "Traslado" al publicar; editor de vehículos, lugares, tramos, tarifa y reglas; agenda de cada vehículo |
| 4. Búsqueda y ficha | Buscar por origen, destino, día y pasajeros; ficha y reserva web; "¿Te buscamos en el aeropuerto?" desde la reserva de un alojamiento |

Cómo quedó la etapa 1 (`app/services/precios_traslado.py`, `app/services/traslados.py`,
migración 0016): solo backend.

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
