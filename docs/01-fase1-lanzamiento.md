# Fase 1: Lanzamiento web de alojamientos

**Documento 01 · Especificación de producto (PRD)**
Versión 0.1 · Septiembre 2026 · Depende de: `00-vision-general.md`

---

## 1. Objetivo

Poner en línea una web donde los prestadores publiquen alojamientos y los viajeros los encuentren, reserven y paguen, con la comisión de la plataforma cobrada automáticamente según reglas configurables.

## 2. Metas

| Meta | Indicador | Objetivo inicial |
|---|---|---|
| Oferta publicada | Prestadores activos con al menos una publicación aprobada | Todos los prestadores ya interesados, en el primer mes |
| Uso real | Reservas pagadas por mes | A definir con los prestadores iniciales |
| Conversión | Búsquedas que terminan en reserva | Medir línea base en el primer mes |
| Confiabilidad | Dobles reservas | Cero |
| Autonomía | Publicaciones creadas sin ayuda del equipo | Mayoría a partir del segundo mes |

## 3. Fuera de alcance en esta fase

| Tema | Motivo |
|---|---|
| Excursiones, gastronomía, traslados | Fase 2; el modelo ya los contempla |
| Programa de beneficios y puntos | Fase 2; en Fase 1 solo cupones simples |
| App móvil | Fase 3; la web es responsive |
| Paquetes combinados | Fase 3 |
| Channel manager completo (sincronización de precios) | Alta complejidad; se cubre con iCal |
| Varios idiomas | Se evalúa según demanda |

## 4. Historias de usuario

### Viajero
1. Como viajero, quiero buscar por destino, fechas y cantidad de personas para ver solo opciones disponibles.
2. Como viajero, quiero filtrar por precio, tipo, servicios (pileta, mascotas, WiFi, cochera) y ver resultados en un mapa.
3. Como viajero, quiero ver fotos, descripción, ubicación, políticas y reseñas antes de reservar.
4. Como viajero, quiero ver el precio total desglosado (noches, limpieza, cargos) antes de pagar.
5. Como viajero, quiero pagar con Mercado Pago el total o una seña.
6. Como viajero, quiero recibir la confirmación por correo y WhatsApp.
7. Como viajero, quiero ver mis reservas, cancelarlas según la política y escribir una reseña después de la estadía.
8. Como viajero, quiero guardar alojamientos en favoritos.
9. Como viajero, quiero enviar una consulta al prestador antes de reservar.

### Prestador
10. Como prestador, quiero registrarme, cargar mis datos fiscales y vincular mi cuenta de Mercado Pago.
11. Como prestador, quiero crear una publicación con fotos, servicios, reglas y varias unidades.
12. Como prestador, quiero definir tarifas por temporada, estadía mínima, cargo de limpieza y descuento por estadías largas.
13. Como prestador, quiero bloquear fechas y sincronizar mi calendario con Booking y Airbnb.
14. Como prestador, quiero elegir entre confirmación inmediata o solicitud a aprobar.
15. Como prestador, quiero ver mis reservas, cobros y comisiones descontadas.
16. Como prestador, quiero responder consultas y reseñas.

### Operador de la plataforma
17. Como operador, quiero aprobar o rechazar publicaciones antes de que sean visibles.
18. Como operador, quiero crear y editar reglas de comisión y probarlas con un simulador.
19. Como operador, quiero ver todas las reservas, pagos y comisiones con filtros y exportación.
20. Como operador, quiero gestionar cancelaciones, reclamos y moderar reseñas.
21. Como operador, quiero administrar provincias, localidades, tipos de alojamiento y servicios disponibles.

## 5. Requisitos

### P0: imprescindibles

**R1. Registro e ingreso**
- Correo y contraseña, e ingreso con Google.
- Verificación de correo y teléfono.
- Roles: viajero, prestador, operador (un usuario puede ser viajero y prestador).
- [ ] No se puede reservar sin correo verificado.
- [ ] Un prestador no puede publicar sin datos fiscales y cuenta de cobro vinculada.

**R2. Publicaciones y unidades**
- Datos: título, tipo, descripción, ubicación en mapa, fotos (mínimo 5), servicios, reglas de la casa, horarios de ingreso y salida, capacidad.
- Varias unidades por publicación, cada una con su capacidad y tarifas.
- Estados: borrador, en revisión, aprobada, pausada, rechazada.
- [ ] Solo las publicaciones aprobadas aparecen en búsquedas.
- [ ] Las fotos se optimizan automáticamente.

**R3. Tarifas y disponibilidad**
- Tarifa base por noche, tarifas por temporada, precio distinto por día de la semana.
- Estadía mínima y máxima, anticipación mínima.
- Cargos adicionales: limpieza, persona extra, mascota.
- Descuentos por estadía semanal o mensual.
- Bloqueo manual de fechas.
- Importación y exportación de calendario iCal.
- [ ] Una fecha reservada o bloqueada en otra plataforma no puede reservarse aquí.
- [ ] Mientras un viajero está pagando, las fechas quedan retenidas por un tiempo limitado.

**R4. Búsqueda**
- Por destino (provincia, localidad o punto en mapa), fechas y personas.
- Filtros: precio, tipo, servicios, calificación, confirmación inmediata.
- Orden: relevancia, precio, calificación, distancia.
- Vista de lista y de mapa.
- Páginas públicas por destino optimizadas para buscadores.
- [ ] Solo muestra unidades con disponibilidad real para las fechas indicadas.

**R5. Reserva**
- Resumen con desglose de precio y política de cancelación.
- Confirmación inmediata o por solicitud (el prestador tiene un plazo para aprobar; si no responde, se cancela y se reintegra).
- Estados: pendiente de pago, pendiente de aprobación, confirmada, cancelada, completada, en reclamo.
- [ ] El precio mostrado al inicio coincide con el cobrado.
- [ ] Una reserva no pagada en el plazo se libera automáticamente.

**R6. Pagos**
- Mercado Pago en modo marketplace, con la comisión separada automáticamente.
- Pago total o seña configurable por prestador.
- Reintegros totales o parciales según política.
- Registro de cada movimiento vinculado a la reserva.
- [ ] Cada pago guarda el monto al prestador, la comisión y el IVA de la comisión.
- [ ] Las notificaciones de Mercado Pago se procesan de forma segura y sin duplicados.

**R7. Motor de comisiones**
- Según la especificación del documento 00, sección 7.
- Pantalla de reglas con alta, edición, vigencia y prioridad.
- Simulador de casos.
- Historial de cambios.
- [ ] Toda reserva registra la regla aplicada y los montos resultantes.
- [ ] Modificar una regla no altera reservas ya creadas.
- [ ] Siempre existe una regla por defecto.

**R8. Políticas de cancelación**
- Plantillas: flexible, moderada, estricta (porcentajes y plazos editables por el operador).
- Cada publicación elige una.
- [ ] El reintegro se calcula automáticamente al cancelar.

**R9. Notificaciones**
- Correo y WhatsApp para: nueva reserva, confirmación, recordatorio previo, cancelación, pedido de reseña.
- [ ] El prestador recibe aviso inmediato de cada reserva o consulta.

**R10. Paneles**
- Viajero: reservas, favoritos, mensajes, datos personales.
- Prestador: publicaciones, calendario, reservas, cobros y comisiones, mensajes, reseñas.
- Operador: aprobaciones, reservas, pagos, comisiones, reclamos, catálogos, usuarios.

**R11. Legal**
- Términos y condiciones, política de privacidad y de cancelación visibles y aceptados al registrarse y al reservar.

### P1: deseables

- Mensajería interna entre viajero y prestador (en P0 alcanza con consulta por formulario y aviso por WhatsApp).
- Cupones de descuento simples creados por el operador o el prestador.
- Reseñas con calificación por categoría (limpieza, ubicación, atención).
- Insignias de "prestador verificado".
- Reportes descargables para el prestador.
- Liquidación mensual de comisiones con factura.

### P2: considerar en el diseño

- Beneficios, puntos y niveles (Fase 2).
- Otros tipos de servicio con reserva por turno o por cupo (Fase 2).
- Reservas con varios ítems y varios prestadores (Fase 3).
- API consumible por app móvil (Fase 3).

## 6. Pantallas

| Pública | Viajero | Prestador | Operador |
|---|---|---|---|
| Inicio con buscador | Mis reservas | Panel resumen | Panel resumen |
| Resultados (lista y mapa) | Detalle de reserva | Publicaciones | Aprobación de publicaciones |
| Ficha de publicación | Favoritos | Editor de publicación | Reglas de comisión |
| Checkout | Perfil | Calendario y tarifas | Simulador de comisiones |
| Páginas por destino | Mensajes | Reservas | Reservas y pagos |
| Registro e ingreso | | Cobros y comisiones | Reclamos |
| Sumá tu alojamiento | | Datos fiscales y cobro | Catálogos y usuarios |

## 7. Flujo principal de reserva

1. El viajero busca y elige una unidad y fechas.
2. El sistema calcula precio y comisión, y retiene las fechas.
3. El viajero confirma y paga en Mercado Pago.
4. Mercado Pago notifica el pago aprobado.
5. Si es confirmación inmediata, la reserva queda confirmada. Si es por solicitud, el prestador aprueba o rechaza dentro del plazo.
6. Se notifica a ambas partes y se actualiza el calendario (incluido el iCal exportado).
7. Tras la estadía, la reserva pasa a completada y se solicita reseña.

## 8. Plan de trabajo sugerido

| Bloque | Contenido |
|---|---|
| 1 | Base técnica, usuarios y roles, catálogos de ubicaciones y tipos |
| 2 | Publicaciones, unidades, fotos, aprobación |
| 3 | Tarifas, disponibilidad, iCal |
| 4 | Búsqueda, ficha, páginas por destino |
| 5 | Motor de comisiones y simulador |
| 6 | Reserva, pagos, cancelaciones, notificaciones |
| 7 | Paneles, legales, pruebas con prestadores iniciales |
| 8 | Lanzamiento controlado y ajustes |

Recomendación: lanzamiento controlado primero con los prestadores ya interesados, antes de abrir el alta pública.

## 9. Preguntas abiertas

| Pregunta | Responsable | Bloqueante |
|---|---|---|
| Porcentajes y plazos de las políticas de cancelación | Dirección | Sí |
| Comisión por defecto y quién la paga (prestador, viajero o ambos) | Dirección | Sí |
| Plazo de retención de fechas durante el pago | Técnica | No |
| Plazo del prestador para aprobar solicitudes | Dirección | No |
| Requisitos de verificación del prestador (habilitación, identidad) | Dirección / Legal | Sí |
| Proveedor de WhatsApp para notificaciones | Técnica | No |
| Cómo y cuándo se factura la comisión | Contable | Sí |
