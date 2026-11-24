# Fase 2: Beneficios y nuevos servicios

**Documento 02 · Especificación de producto (PRD)**
Versión 0.1 · Septiembre 2026 · Depende de: `00-vision-general.md`, `01-fase1-lanzamiento.md`

---

## 1. Objetivo

Aumentar la recurrencia de los viajeros con un programa de beneficios cofinanciado, y ampliar la oferta con excursiones, gastronomía y traslados reservables con el mismo motor de reservas, pagos y comisiones.

## 2. Metas

| Meta | Indicador |
|---|---|
| Fidelización | % de viajeros con más de una reserva en 12 meses |
| Adopción del programa | % de reservas que usan algún beneficio |
| Participación de prestadores | % de prestadores que ofrecen beneficios propios |
| Participación de sponsors | Cantidad de campañas cofinanciadas activas |
| Venta cruzada | % de reservas de alojamiento con al menos un servicio adicional |

## 3. Fuera de alcance en esta fase

| Tema | Motivo |
|---|---|
| Paquetes con varios servicios en un único pago | Fase 3 |
| App móvil | Fase 3 |
| Canje de puntos por productos físicos | Complejidad logística |
| Puntos transferibles entre usuarios | Riesgo de fraude |

---

## Parte A: Programa de beneficios

### 4. Componentes

**Niveles del viajero**
- Niveles configurables (ej. Explorador, Viajero, Búho) según reservas completadas o monto acumulado en un período.
- Cada nivel otorga ventajas: descuentos, servicios gratis, prioridad, mejoras de categoría.

**Puntos**
- Se acumulan por reservas completadas y acciones (reseñas, completar perfil, invitar amigos).
- Se canjean como descuento en futuras reservas.
- Vencimiento configurable.
- Se acreditan recién cuando la reserva se completa (no al pagar), para evitar abusos con cancelaciones.

**Cupones y promociones**
- Código o aplicación automática.
- Tipo: porcentaje, monto fijo, noche gratis, servicio adicional gratis.
- Condiciones: destino, tipo de servicio, fechas, monto mínimo, nivel del viajero, primera reserva, cantidad de usos.

**Campañas con sponsor**
- Un sponsor (ej. organismo de turismo provincial) financia un beneficio con presupuesto tope.
- Al agotarse el presupuesto, la campaña se cierra automáticamente.
- Reporte de uso para rendición al sponsor.

**Beneficios de prestadores**
- Cada prestador puede ofrecer descuentos exclusivos para usuarios registrados o por nivel, a cambio de mayor visibilidad en búsquedas.

### 5. Financiamiento mixto

Cada beneficio define **quién absorbe el costo** y en qué proporción:

| Financiador | Ejemplo |
|---|---|
| Plataforma | Descuento de bienvenida; se descuenta de la comisión |
| Prestador | 10% para nivel Búho; se descuenta de su cobro |
| Sponsor | 15% en cabañas de una provincia; la plataforma lo recupera del sponsor |
| Combinado | 50% prestador, 50% plataforma |

**Reglas**
- La reserva registra el desglose del descuento por financiador.
- La parte del sponsor genera una cuenta a cobrar con su liquidación periódica.
- Se define si la comisión se calcula sobre el precio antes o después del descuento (configurable por regla).
- Tope de beneficios acumulables por reserva.

### 6. Historias de usuario

1. Como viajero, quiero ver mi nivel, mis puntos y cuánto me falta para el siguiente nivel.
2. Como viajero, quiero ver los precios con mi beneficio ya aplicado en la búsqueda.
3. Como viajero, quiero canjear puntos al pagar.
4. Como prestador, quiero ofrecer descuentos a viajeros de ciertos niveles y ver cuántas reservas me generan.
5. Como operador, quiero crear campañas con sponsor, con presupuesto y reporte.
6. Como sponsor, quiero ver el uso y el impacto de mi campaña.

### 7. Requisitos P0

- [ ] Configuración de niveles, puntos, vencimientos y reglas de acumulación.
- [ ] Motor de promociones con condiciones combinables.
- [ ] Desglose de financiamiento en cada reserva.
- [ ] Panel del sponsor con presupuesto, uso y reporte exportable.
- [ ] Reversión de puntos y beneficios si la reserva se cancela.
- [ ] Límite de beneficios acumulables por reserva.
- [ ] Registro de auditoría de todos los movimientos de puntos.

### 8. Requisitos P1

- Programa de referidos (invitar amigos).
- Beneficios por cumpleaños.
- Alianzas con comercios locales (descuentos presentando la reserva).

---

## Parte B: Nuevos tipos de servicio

### 9. Tipos y forma de reserva

| Tipo | Se reserva por | Ejemplos |
|---|---|---|
| Alojamiento | Noches | Cabañas, casas, hoteles (Fase 1) |
| Excursión / actividad | Fecha, turno y cupo por persona | Cabalgatas, trekking, visitas a bodegas |
| Gastronomía | Fecha, horario y cantidad de comensales | Cenas, degustaciones, menús especiales |
| Traslado | Fecha, horario, origen, destino y pasajeros | Aeropuerto, entre localidades |

### 10. Requisitos P0

**Modelo de reserva por turno y cupo**
- [x] Turnos recurrentes (ej. martes y jueves a las 9) y excepciones (docs/05, etapa 1).
- [x] Cupo por turno con descuento automático al reservar (docs/05).
- [x] Precios por tipo de pasajero (adulto, menor, jubilado): los define cada prestador (docs/05).
- [x] Mínimo de participantes con cancelación automática si no se alcanza: mínimo y aviso por turno (docs/05).

**Traslados**
- [ ] Tarifa por tramo, por kilómetro o por vehículo.
- [ ] Capacidad del vehículo y equipaje.

**Venta cruzada**
- [ ] Al confirmar un alojamiento, sugerir servicios cercanos para esas fechas.
- [x] En la ficha del alojamiento, mostrar servicios de la zona (excursiones de la localidad, docs/05).

**Comisiones**
- [ ] El motor de comisiones aplica reglas por cada tipo y subtipo de servicio sin cambios estructurales.

**Prestadores de servicios**
- [ ] Alta con los datos propios de cada rubro. La plataforma no pide habilitaciones ni seguros (decisión de Dirección, noviembre 2026).
- [ ] Panel adaptado a turnos y cupos.

### 11. Requisitos P1

- Punto de encuentro y recorrido en mapa para excursiones.
- Check-in de participantes con código QR.
- Reseñas específicas por guía o conductor.

---

## 12. Preguntas abiertas

| Pregunta | Responsable | Bloqueante |
|---|---|---|
| Nombres y umbrales de los niveles | Dirección / Marketing | Sí |
| Valor del punto y vencimiento | Dirección | Sí |
| Comisión sobre precio con o sin descuento | Dirección | Sí |
| Tratamiento fiscal de los aportes de sponsors | Contable | Sí |
