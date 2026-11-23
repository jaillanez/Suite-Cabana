# Salones de eventos

**Documento 04 · Especificación de producto (PRD)**
Versión 0.1 · Noviembre 2026 · Depende de: `00-vision-general.md`, `01-fase1-lanzamiento.md`.
Adelanta: un tipo de servicio nuevo (Fase 2) y el *paquete de prestador* (`03 §8`).

---

## 1. Objetivo

Que un propietario publique su salón de eventos —solo o junto a sus cabañas— con
disponibilidad, capacidad, comodidades y precios propios, y que el viajero lo
reserve y señe online con el mismo circuito que un alojamiento.

Es habitual que los complejos de cabañas tengan salón o quincho. Hoy no lo pueden
publicar: el modelo lo prevé (`00 §6`, tipo de servicio genérico) pero la lógica
de precios, disponibilidad y búsqueda asume noches de alojamiento.

## 2. Decisiones tomadas

| Tema | Decisión |
|---|---|
| Cómo se alquila | Por **franjas fijas** que define el propietario y/o **por horas**, en el mismo salón |
| Disponibilidad | Por **rango de hora** (no por día). Una jornada es una franja larga |
| Pago | **Seña online**; el porcentaje lo elige el propietario y el saldo se arregla con él |
| Comisión | La **misma regla** que las cabañas, calculada **sobre el total** del evento |
| Cancelación | Política "Eventos": hasta 30 días antes se devuelve el **90 %**, hasta 15 días el **50 %**, después nada. Nunca el 100 %: el 10 % queda siempre |
| Reintegro | Sobre **lo pagado** (la seña), no sobre el total: no se devuelve plata que no entró |
| Confirmación | **A solicitud** por defecto: el propietario aprueba antes de confirmar |
| Salón + cabañas | **Incluido**: una sola reserva con varios ítems, del mismo propietario |
| Anticipación | Un salón se reserva hasta **24 meses** antes (las cabañas, 12). Las cabañas de un paquete siguen al evento |

Con cobro directo la comisión no se retiene en el pago: queda en el snapshot y se
factura aparte, como las cabañas.

## 3. Fuera de alcance

- Garantía por daños cobrada por la plataforma (sería custodiar dinero ajeno). La
  pide el propietario en persona.
- Paquetes entre **distintos** propietarios (`03 §8`, paquete curado): cada pago
  entra en una sola cuenta de Mercado Pago.
- Sincronizar el calendario del salón con calendarios externos. Se bloquea a mano.

## 4. Formas de alquilar

El propietario elige, por cada salón, una o las dos:

**Franjas fijas.** Las define él: nombre, horario y precio por día de la semana.
Ej.: "Mañana 9 a 14 h", "Noche 21 a 5 h". El viajero elige una.

**Por horas.** El viajero elige inicio y cantidad de horas. El propietario define:
- precio por hora (por día de la semana) y mínimo de horas;
- horario de atención (ej. 10 a 2 h);
- recargo nocturno o de fin de semana, opcional;
- **tiempo de preparación** entre eventos (ej. 1 h de limpieza), que se bloquea solo.

Las dos formas comparten disponibilidad: reservada la "Noche", nadie toma 22 a 24 h.

## 5. Requisitos

**S1. Tipo de servicio.** "Salón de eventos", con subtipos salón, quincho y espacio
al aire libre, y modo de reserva **por horario**.

**S2. Disponibilidad por hora.** Bloqueos por rango de fecha y hora, con
restricción de exclusión en la base: dos rangos de la misma unidad no se pisan
(mismo principio que las noches, `CLAUDE.md` §6). Zona horaria argentina; los
rangos pueden cruzar la medianoche. Las cabañas siguen por día, sin cambios.

**S3. Capacidad.** Sentados y de pie (cóctel), además de capacidad base y cargo por
persona extra.

**S4. Comodidades por tipo.** Cada comodidad pertenece a uno o varios tipos de
servicio. De salón: equipo de sonido, pista de baile, mesas y sillas, cocina,
parrilla, aire acondicionado, grupo electrógeno, estacionamiento, accesibilidad.

**S5. Adicionales con precio.** Vajilla, sonido, limpieza, mozos, etc. Precio por
evento o por persona. Entran en el desglose y en la base de la comisión.

**S6. Reglas del lugar.** Música hasta qué hora, catering propio permitido o no,
decoración, menores, etc.

**S7. Seña.** Porcentaje por salón (o del propietario). Se cobra la seña online; la
reserva se confirma con la seña aprobada; el saldo queda registrado como pendiente
con el propietario. El chequeo de monto (`registrar_pago`) compara contra la seña.

**S8. Cancelación para eventos.** Políticas con plazos más largos (ej. 30 y 15 días).

**S9. Búsqueda separada.** Los salones no aparecen entre los alojamientos (hoy
aparecerían: la búsqueda no filtra por tipo). Sección propia: fecha, horario o
duración, invitados y localidad.

**S10. Ficha del salón.** Capacidades, comodidades, adicionales, reglas, mapa
aproximado y un **calendario del día** con horas libres y ocupadas.

**S11. Paquete salón + cabañas.** Desde la ficha del salón (o de las cabañas), el
viajero suma unidades del **mismo propietario**: una reserva, varios ítems
(`ItemReserva`), un solo pago. Reglas:
- La disponibilidad de todos los ítems se toma en la misma transacción: o se
  retienen todos, o ninguno.
- Cada ítem guarda su propio snapshot de comisión.
- La seña se calcula sobre el total del paquete.
- Cancelación: cada ítem con su política; el reintegro es la suma.
- El propietario lo aprueba o rechaza entero.

**S12. Textos.** Ficha, detalle de reserva, paneles y correos en lenguaje de evento:
"sábado 15, de 15 a 18 h, 40 invitados", no "1 noche, 40 huéspedes".

## 6. Etapas

Cada etapa se puede publicar por separado. Hechas (noviembre 2026): **1**, **2**
(API de precio y reserva), **3** (el propietario carga su salón), **4** (sección
Salones, ficha, reserva con seña desde la web y el detalle de la reserva en
lenguaje de evento), **5** (agenda por horas de cada espacio, bloqueos a mano,
reservas recibidas con horario e invitados) y **6** (el paquete). Falta la **7**,
que depende de los datos del propietario.

Cómo quedó el paquete (S11):
- Desde el panel de reserva del salón, "¿Se quedan a dormir?" lista las unidades
  del mismo anfitrión para las noches desde el día del evento, con precio y si
  están libres (`GET /salones/unidades/{id}/alojamientos`). Las elegidas viajan en
  `alojamientos` de la cotización y de la reserva.
- Las noches tienen que tocar el evento (se puede llegar antes o irse después).
  Hasta 6 alojamientos por reserva.
- La seña es la del salón, sobre el total del paquete.
- Cada ítem guarda su snapshot de política (`item_reserva.politica_cancelacion`,
  migración 0012). El reintegro reparte lo pagado entre los ítems según lo que vale
  cada uno y aplica a cada parte su política y su fecha.
- Si alguna parte es "a solicitud", el paquete entero espera la aprobación.

| Etapa | Contenido |
|---|---|
| 1. Base | Tipo y subtipos; comodidades por tipo; capacidades; bloqueos por hora con exclusión; búsqueda de alojamientos sin salones. Tests de superposición y concurrencia |
| 2. Precio y reserva | Franjas y horas; mínimos, horario de atención, recargos, preparación; adicionales; seña; políticas de eventos |
| 3. Alta y edición | "Salón de eventos" al publicar; editor de capacidades, franjas, horas, adicionales y reglas |
| 4. Búsqueda y ficha | Sección Salones, búsqueda, ficha con calendario del día, enlace salón ↔ cabañas |
| 5. Reservas y agenda | Detalle y correos de evento; agenda por horas; bloqueo manual por horas |
| 6. Paquete | Salón + cabañas del mismo propietario en una reserva (S11) |
| 7. Los Búhos | Su salón con las fotos de `fotos/los-buhos/salon/` y datos reales |

## 7. Preguntas abiertas

| Pregunta | Responsable | Bloqueante |
|---|---|---|
| Datos reales del salón de Los Búhos (capacidad, precios, horarios) | Propietario | Etapa 7 |
