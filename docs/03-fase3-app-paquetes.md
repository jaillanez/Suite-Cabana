# Fase 3: App móvil y paquetes

**Documento 03 · Especificación de producto (PRD)**
Versión 0.1 · Septiembre 2026 · Depende de: documentos 00, 01 y 02

---

## 1. Objetivo

Llevar la experiencia al celular con una app para viajeros y prestadores, y permitir armar y vender paquetes que combinen alojamiento y servicios de distintos prestadores en una sola compra.

## 2. Metas

| Meta | Indicador |
|---|---|
| Adopción de la app | % de reservas hechas desde la app |
| Gestión móvil | % de prestadores que operan desde la app |
| Paquetes | % de ventas que son paquetes y ticket promedio frente a reservas simples |
| Recurrencia | Viajeros activos mensuales en la app |

## 3. Fuera de alcance en esta fase

| Tema | Motivo |
|---|---|
| Vuelos y transporte de larga distancia | Otro tipo de negocio e integraciones |
| Venta a agencias (B2B) | Evaluar después de validar paquetes |
| Guía turística con contenido editorial extenso | No es el foco del marketplace |

---

## Parte A: App móvil

### 4. Enfoque

- Una sola app con modo viajero y modo prestador.
- Desarrollo multiplataforma (iOS y Android) sobre la misma API de las fases anteriores.
- Sin lógica de negocio propia en la app: todo cálculo (precios, comisiones, beneficios) queda en el backend.

### 5. Requisitos P0: viajero

- [ ] Búsqueda, ficha, reserva y pago con la misma funcionalidad que la web.
- [ ] Notificaciones push (confirmaciones, recordatorios, promociones).
- [ ] Reservas disponibles sin conexión (datos, dirección, contacto).
- [ ] Cómo llegar: apertura en la app de mapas del teléfono.
- [ ] Nivel, puntos y beneficios.
- [ ] Mensajería con el prestador.
- [ ] Búsqueda "cerca mío" con ubicación del dispositivo.
- [ ] Voucher o QR de cada reserva y servicio.

### 6. Requisitos P0: prestador

- [ ] Aviso inmediato de reservas y consultas.
- [ ] Aprobar o rechazar solicitudes.
- [ ] Calendario con bloqueo rápido de fechas.
- [ ] Carga de fotos desde el teléfono.
- [ ] Lectura de QR para registrar el ingreso o la participación.
- [ ] Resumen de cobros.

### 7. Requisitos P1

- Ingreso con huella o reconocimiento facial.
- Compartir alojamientos y planificar el viaje con otros usuarios.
- Accesos directos y widgets.

---

## Parte B: Paquetes

### 8. Tipos de paquete

| Tipo | Quién lo arma | Ejemplo |
|---|---|---|
| Armado por el viajero | El viajero, en su carrito | Cabaña 3 noches + excursión + traslado |
| Paquete de prestador | Un prestador con sus propios servicios | Complejo con cena incluida |
| Paquete curado | La plataforma, combinando prestadores | "Fin de semana en el valle" |

### 9. Requisitos P0

**Carrito**
- [ ] Varios ítems de distintos prestadores en una sola compra.
- [ ] Validación de compatibilidad de fechas y horarios (ej. excursión dentro de la estadía).
- [ ] Precio total con desglose por ítem.

**Paquetes curados**
- [ ] Composición con ítems fijos y opcionales.
- [ ] Precio de paquete con descuento respecto de la suma de ítems, con definición de qué prestador absorbe cuánto.
- [ ] Disponibilidad calculada como la intersección de la disponibilidad de todos los ítems.

**Pago y comisiones**
- [ ] Una comisión por ítem según el motor de reglas, más una comisión o recargo opcional del paquete.
- [ ] Distribución del cobro a cada prestador.

**Cancelaciones**
- [ ] Política propia del paquete o combinación de las políticas de cada ítem (definir).
- [ ] Qué ocurre si un prestador cancela un ítem: reemplazo, reintegro parcial o cancelación total.

### 10. Desafío técnico principal: cobro a varios prestadores

El modo marketplace de Mercado Pago está pensado para un vendedor por pago. Alternativas para un paquete con varios prestadores:

| Opción | Ventaja | Riesgo |
|---|---|---|
| Un pago por prestador en el mismo checkout | La plataforma no custodia dinero | Experiencia de pago más compleja; un pago puede fallar y otro no |
| Cobro centralizado y posterior transferencia a cada prestador | Un solo pago para el viajero | La plataforma custodia fondos: implicancias fiscales y regulatorias |
| Operar como agencia de viajes para paquetes curados | Marco legal claro para vender paquetes | Requiere habilitación como agencia |

Debe resolverse antes de iniciar el desarrollo de esta parte.

### 11. Requisitos P1

- Paquetes sugeridos automáticamente según el historial del viajero.
- Pago en cuotas del paquete completo.
- Paquetes para grupos y eventos.

---

## 12. Preguntas abiertas

| Pregunta | Responsable | Bloqueante |
|---|---|---|
| Modelo de cobro para paquetes con varios prestadores | Dirección / Contable / Legal | Sí |
| ¿Se requiere habilitación como agencia de viajes para vender paquetes? | Legal | Sí |
| Política de cancelación de paquetes | Dirección | Sí |
| Tecnología de la app (multiplataforma a definir) | Técnica | No |
| Publicación en tiendas: cuentas y titularidad | Dirección | No |
