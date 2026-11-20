# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Tres audiencias de peso equivalente. Ninguna es secundaria: cuando haya que elegir, se resuelve por caso, no subordinando una a otra (confirmado por el equipo, 2026-09-16).

- **Viajero** (visitante sin cuenta y viajero registrado). Planifica una escapada dentro de Argentina: busca por destino, fechas y cantidad de personas; compara; reserva y paga en línea. Su fricción real es la desconfianza de pagar por adelantado a un desconocido y la falta de medios de pago locales en las plataformas extranjeras. Registrado además: reseña, favoritos, y beneficios desde la Fase 2.
- **Prestador**. Dueño o responsable de un alojamiento (cabañas, casas, departamentos, hosterías, hoteles). Hoy opera con Booking/Airbnb y WhatsApp. Necesita autogestionar publicación, calendario, tarifas por temporada, reservas y cobros sin ayuda del equipo, y ver con claridad cuánto cobra y cuánta comisión se le descontó. No es un usuario técnico y muchas tareas las hace desde el teléfono.
- **Operador de la plataforma**. Uso interno e intensivo: aprueba publicaciones, crea y prueba reglas de comisión, revisa reservas y pagos, gestiona cancelaciones, reclamos, moderación de reseñas y catálogos.
- **Sponsor** (organismo de turismo, municipio, comercio). Cofinancia beneficios y campañas. Recién entra como usuario en la Fase 2; el modelo debe dejarle lugar.

## Product Purpose

Marketplace turístico argentino donde los prestadores publican su oferta y los viajeros buscan, reservan y pagan dentro de la plataforma. La plataforma cobra una comisión configurable por reserva y no custodia el dinero del prestador (acreditación separada en el cobro).

Existe porque los prestadores locales dependen de plataformas extranjeras con comisiones altas, sin medios de pago argentinos y sin fidelización de la oferta local; y los portales nacionales son, en su mayoría, clasificados sin pago integrado ni programa de beneficios.

Éxito de la Fase 1 (docs/01 §2):
- Todos los prestadores ya interesados con al menos una publicación aprobada en el primer mes.
- Reservas pagadas por mes (objetivo a definir con los prestadores iniciales).
- Conversión de búsqueda a reserva: medir línea base en el primer mes.
- **Cero dobles reservas.**
- Mayoría de publicaciones creadas sin ayuda del equipo a partir del segundo mes.

## Positioning

Lo que un portal vecino no puede copiar sin construirlo:

1. **Motor de comisiones multidimensional con snapshot.** La comisión se resuelve por tipo de servicio, ubicación, prestador, publicación, temporada, fecha de reserva, monto y antigüedad del prestador; con porcentaje y/o monto fijo, mínimos y máximos, reparto configurable entre prestador y viajero, e IVA incluido o adicional. Cada reserva guarda la regla aplicada y sus montos, así que cambiar una regla nunca altera reservas existentes. Habilita promociones reales (ej. primeros 3 meses sin comisión) sin migrar datos.
2. **Cobro en modo marketplace con medios de pago argentinos.** Mercado Pago acredita comisión y pago al prestador en una sola operación; la plataforma no custodia fondos ajenos. Pago total o seña configurable por prestador.
3. **Modelo de servicio genérico desde el día uno.** Alojamiento es solo el primer tipo; excursiones, gastronomía y traslados entran sin rehacer el modelo, y la reserva ya soporta varios ítems (paquetes, Fase 3).
4. **Beneficios cofinanciados.** Plataforma, prestador y sponsor pueden financiar el mismo beneficio (Fase 2): fidelización local que una plataforma extranjera no ofrece.

## Operating Context

- **Web responsive** como único canal en Fase 1. App móvil en Fase 3, consumiendo la misma API.
- **Alcance nacional.** Provincia → localidad → zona, con búsqueda por mapa y distancia (PostGIS). Páginas públicas por destino pensadas para buscadores.
- **El calendario vive en varias plataformas.** El prestador ya publica en Booking/Airbnb; la sincronización iCal (importación y exportación) es parte del uso normal, no un extra.
- **WhatsApp y correo** son los canales reales de aviso a prestadores y viajeros (nueva reserva, confirmación, recordatorio, cancelación, pedido de reseña).
- **Trámite fiscal previo a publicar.** El prestador no puede publicar sin datos fiscales cargados y cuenta de cobro vinculada.
- **Aprobación humana.** Ninguna publicación es visible sin que un operador la apruebe.
- **Lanzamiento controlado.** Primero los prestadores ya comprometidos, después el alta pública.
- Idioma de la interfaz, los datos y el código: **español rioplatense (es-AR)**. Moneda operativa: peso argentino.

## Capabilities and Constraints

**Alcance confirmado de Fase 1** (docs/01 §5): registro con correo/contraseña y Google, verificación de correo y teléfono, roles viajero/prestador/operador (acumulables); publicaciones con varias unidades, fotos (mínimo 5) y estados borrador→revisión→aprobada/pausada/rechazada; tarifas por temporada y día de la semana, estadía mínima/máxima, cargos (limpieza, persona extra, mascota), descuentos por estadía larga, bloqueos e iCal; búsqueda con filtros, orden, lista y mapa; reserva con desglose de precio y política de cancelación, confirmación inmediata o por solicitud; pagos y reintegros por Mercado Pago; motor de comisiones con pantalla de reglas, simulador e historial; plantillas de cancelación flexible/moderada/estricta; notificaciones; paneles de viajero, prestador y operador; textos legales aceptados al registrarse y al reservar.

**Fuera de alcance en Fase 1:** excursiones, gastronomía y traslados (Fase 2, ya contemplados en el modelo); beneficios y puntos (Fase 2, en Fase 1 solo cupones simples); app móvil (Fase 3); paquetes combinados (Fase 3); channel manager completo de precios; multi-idioma.

**Restricciones técnicas no negociables** (CLAUDE.md, docs/00 §7):
- Toda la lógica de negocio —precio, comisión, beneficios, disponibilidad— se calcula en el backend. El frontend y la futura app solo muestran.
- Dinero en `Decimal` (`Numeric(14,2)`). Nunca `float`.
- Cero dobles reservas: retención de fechas con vencimiento y control de concurrencia en la base.
- Webhooks de Mercado Pago idempotentes: se registran por id y se procesan una sola vez.
- Toda reserva tiene `ItemReserva` y `ComisionAplicada` (snapshot).
- El precio mostrado al inicio del flujo debe coincidir con el cobrado.
- Código, tablas y endpoints en español, `snake_case`; API versionada en `/api/v1`; esquema solo por migraciones Alembic.

**Terminología** (usarla tal cual en interfaz y código): prestador, publicación (ficha pública), unidad (lo que realmente se reserva), regla de comisión, seña, iCal.

**Decisiones de producto explícitamente abiertas** — registrar como pendientes, nunca inventarlas:
- Nombre público y dominio definitivos (ver Brand Commitments).
- Porcentajes y plazos de las políticas de cancelación *(bloqueante, Fase 1)*.
- Comisión por defecto y quién la paga: prestador, viajero o reparto *(bloqueante, Fase 1)*.
- Requisitos de verificación del prestador (habilitación, identidad) *(bloqueante, Fase 1)*.
- Cómo y cuándo se factura la comisión ante ARCA *(bloqueante, Fase 1)*.
- Plazo de retención de fechas durante el pago; plazo del prestador para aprobar solicitudes.
- Pasarela de pago definitiva (Mercado Pago es la propuesta, no la decisión final) y proveedor de WhatsApp.
- Idiomas y monedas adicionales (¿USD para extranjeros?). Hoy: solo es-AR y ARS.
- Términos y condiciones, privacidad (Ley 25.326), botón de arrepentimiento y rol de la plataforma frente a reclamos: a validar con legales.

## Brand Commitments

- **No hay marca definida.** `Suite-Cabana` es el nombre interno del repositorio. "Los Búhos" fue un nombre de trabajo anterior, todavía presente en `frontend/src/app/layout.tsx` (metadata) y en la paleta placeholder de `globals.css` (`--noche`, `--monte`, `--ojo`). **Ninguno de los dos es vinculante para el diseño.**
- Restricción acordada para el nombre público futuro: no debe atar el producto a un solo tipo de servicio (nada de "cabaña" en el nombre), porque desde la Fase 2 se venden excursiones, gastronomía y traslados, y ya en Fase 1 se publican hoteles, departamentos y hosterías.
- **Voz:** español rioplatense con voseo, según la copia ya escrita ("Encontrá dónde quedarte", "Sumá tu alojamiento"). Trato directo con el prestador y con el viajero.
- No existe logo, tipografía de marca ni manual de identidad. Nada que respetar todavía; nada que dar por existente.
- **Preferencia declarada de dirección visual (2026-09-16):** el equipo eligió el estándar de la categoría por sobre las direcciones alternativas propuestas. La convención es el compromiso: se ejecuta el patrón que el viajero ya conoce —barra de búsqueda persistente, filtros, grilla de tarjetas con foto, mapa con precios— a fidelidad completa, sin ironía ni guiños. No es una decisión por defecto ni un punto de partida a superar; se toma en serio y se ejecuta bien.
- **Vara de terminación:** la página tiene que poder ponerse al lado de **Airbnb, Booking y Despegar** sin que se note la diferencia. Eso fija el nivel exigible en densidad de información, velocidad percibida, estados de carga, comportamiento del mapa y convenciones locales de precio en pesos.

## Evidence on Hand

**No hay material real de ningún tipo** (confirmado por el equipo, 2026-09-16):

- Sin fotos de alojamientos.
- Sin publicaciones ni fichas cargadas.
- Sin logo ni identidad visual.
- Sin reseñas, testimonios, métricas de uso, clientes citables ni sponsors confirmados.

Los documentos registran que **ya hay prestadores interesados**, pero ninguno entregó material.

**Primer prestador identificado (2026-09-16): Los Búhos**, en Médano de Oro, departamento
Rawson, San Juan. Es un lugar real y cercano al equipo. Ofrece **las dos cosas**: cabañas
para estadías y alquiler del predio por día, con piletas y salón, para eventos. Lo segundo
no es alojamiento y no entra en el alcance de la Fase 1: necesita un `TipoServicio` propio
(Fase 2), y es la primera prueba concreta de por qué el modelo de servicio es genérico.

Datos que **todavía no se tienen** de Los Búhos y que nadie debe inventar: fotos reales,
cantidad de unidades y capacidad, precios y cargos, dirección exacta, y qué servicios tiene
(wifi, aire, calefacción, mascotas). Hasta que se aporten, la publicación queda marcada
como dato de ejemplo en la base.

**Alcance geográfico de los datos de ejemplo:** provincia de San Juan, con el departamento
Rivadavia como foco. Los 19 departamentos y sus distritos están cargados como catálogo real.

Prohibido, en cualquier superficie: inventar nombres de alojamientos o complejos presentados como reales, reseñas, calificaciones, cantidad de propiedades o de usuarios, logos de sponsors, precios de ejemplo presentados como vigentes, o afirmaciones de cobertura ("X destinos"). Todo contenido de demostración va declarado como tal y debe poder reemplazarse sin rediseñar.

Único contenido real disponible: la especificación en `docs/` y la copia ya escrita en el frontend.

## Product Principles

1. **Genérico desde el día uno.** Alojamiento es el primer `TipoServicio`, no el producto. Nada —modelo, interfaz ni lenguaje— puede cerrarle la puerta a excursiones, gastronomía, traslados o paquetes.
2. **La confianza es la función, no un adorno.** Pagar por adelantado a un desconocido es el salto que hay que hacer fácil: precio total desglosado antes de pagar, políticas de cancelación visibles, disponibilidad real, cero dobles reservas.
3. **El prestador se autogestiona.** Es una meta medida, no una aspiración: la mayoría de las publicaciones deben crearse sin ayuda del equipo, por gente no técnica, muchas veces desde el teléfono.
4. **El backend decide, el cliente muestra.** Un solo lugar donde se calculan precio, comisión, beneficios y disponibilidad, porque la app de Fase 3 consume la misma API.
5. **Las tres audiencias mandan por igual.** Viajero, prestador y operador: ninguna interfaz es "la secundaria" ni recibe menos cuidado por ser interna.

## Accessibility & Inclusion

No se fijó todavía un estándar formal (pendiente de decisión). Necesidades de usuario conocidas que el diseño debe asumir:

- Prestadores no técnicos, de edad y alfabetización digital variadas, operando desde el teléfono y con conexiones irregulares en zonas turísticas.
- Viajeros completando un flujo de pago: los estados de error, el desglose de precio y la política de cancelación tienen que ser legibles sin ayuda.
- El frontend ya declara `lang="es-AR"` y un `:focus-visible` visible; mantener el foco visible y la navegación por teclado como piso mínimo.
