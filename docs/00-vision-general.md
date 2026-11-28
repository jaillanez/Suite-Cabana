# Los Búhos (nombre de trabajo): marketplace turístico

**Documento 00: Visión general, decisiones y arquitectura**
Versión 0.1 · Septiembre 2026 · Estado: borrador para revisión

---

## 1. Problema

Los propietarios de cabañas y los prestadores turísticos locales dependen de plataformas extranjeras (Booking, Airbnb) que cobran comisiones altas, no se adaptan a los medios de pago argentinos y no fidelizan al viajero con la oferta local. Los portales nacionales existentes son, en su mayoría, clasificados sin pago integrado ni programa de beneficios.

## 2. Propuesta

Un marketplace web donde:

- **Prestadores** publican alojamientos y servicios turísticos (excursiones, gastronomía, traslados).
- **Viajeros registrados** buscan, reservan, pagan en línea y acceden a beneficios.
- **La plataforma** cobra una comisión configurable por reserva.
- **Sponsors** (organismos de turismo, municipios, comercios) pueden cofinanciar beneficios.

## 3. Decisiones tomadas

| Tema | Decisión |
|---|---|
| Alcance geográfico | Todo el país |
| Tipos de alojamiento | Todos (cabañas, casas, departamentos, hosterías, hoteles, etc.) |
| Pago | Reserva y pago dentro de la plataforma |
| Ingresos | Comisión por reserva, configurable con la mayor amplitud posible |
| Beneficios para registrados | Sí |
| Financiamiento de beneficios | Mixto (plataforma, prestador, sponsor) |
| Primeros prestadores | Ya hay interesados |
| Servicios | Alojamiento, excursiones, gastronomía y traslados |
| Canal | Web (responsive) en la primera etapa |
| Plazo | Lo antes posible, por fases |

## 4. Actores

| Actor | Qué hace |
|---|---|
| Visitante | Busca y consulta sin registrarse |
| Viajero registrado | Reserva, paga, reseña, acumula beneficios |
| Prestador | Publica, gestiona calendario, precios y reservas; cobra |
| Operador de la plataforma | Aprueba publicaciones, configura comisiones, resuelve reclamos |
| Sponsor | Financia beneficios y campañas (Fase 2) |

## 5. Fases

| Fase | Objetivo | Documento |
|---|---|---|
| 1. Lanzamiento | Alojamientos publicables, reservables y pagables, con comisión configurable | `01-fase1-lanzamiento.md` |
| 2. Beneficios y servicios | Programa de fidelización y nuevos tipos de servicio | `02-fase2-beneficios-servicios.md` |
| 3. App y paquetes | App móvil y paquetes combinados | `03-fase3-app-paquetes.md` |

Principio rector: **todo lo que se construya en la Fase 1 debe estar preparado para las Fases 2 y 3** (el modelo de "servicio" es genérico desde el inicio; los alojamientos son solo el primer tipo).

## 6. Modelo de datos núcleo

```
Prestador ──< Publicacion ──< Unidad ──< Disponibilidad
                   │              └──< Tarifa (por temporada)
                   │
                   └── TipoServicio (alojamiento | excursion | gastronomia | traslado)

Usuario ──< Reserva ──< ItemReserva >── Unidad
               ├──< Pago
               ├──  ComisionAplicada (snapshot)
               └──< Resena

ReglaComision (dimensiones + valor + vigencia + prioridad)
Ubicacion: Provincia ──< Localidad ──< Zona
```

- **Publicacion**: la ficha visible (ej. "Complejo Los Álamos").
- **Unidad**: lo que realmente se reserva (ej. "Cabaña 2, 4 personas"; "Excursión al dique, turno mañana").
- **ItemReserva**: permite que una reserva contenga varios servicios (necesario en Fase 3).
- **ComisionAplicada**: copia de la regla y los montos en el momento de la reserva; los cambios posteriores de reglas no alteran reservas existentes.

## 7. Motor de comisiones (componente central)

### 7.1 Dimensiones de una regla
Todas opcionales; vacía significa "cualquiera".

- Tipo y subtipo de servicio
- Provincia, localidad, zona
- Prestador y publicación específica
- Rango de fechas de estadía o servicio (temporada)
- Rango de fechas de creación de la reserva (promociones)
- Rango de monto de la reserva
- Antigüedad o categoría del prestador (ej. primeros 3 meses sin comisión)

### 7.2 Valor de la regla
- Porcentaje, monto fijo o ambos
- Mínimo y máximo por reserva
- **Quién paga**: prestador, viajero (cargo de servicio) o división en porcentajes
- IVA sobre la comisión: incluido o adicional

### 7.3 Resolución
1. Se filtran las reglas vigentes que coinciden con la reserva.
2. Gana la **más específica** (mayor cantidad de dimensiones definidas). Una dimensión cuenta también las que implica: un subtipo define su tipo, una localidad su provincia, una zona su localidad y provincia, y una publicación todo lo anterior y su prestador. Así "Cabalgatas" le gana a "Excursiones" sin depender de cuál se creó último.
3. Si empatan, gana la de **mayor prioridad** manual.
4. Si siguen empatadas, gana la **más reciente**.
5. Siempre existe una **regla por defecto** (sin dimensiones) que garantiza un resultado.

### 7.4 Herramientas de administración
- Simulador: se ingresa un caso y muestra qué regla aplica y por qué.
- Historial de cambios con usuario y fecha.
- Vista de reglas por provincia y tipo de servicio.

## 8. Pagos

Propuesta: **Mercado Pago en modo marketplace**.

- Cada prestador vincula su cuenta de Mercado Pago a la plataforma.
- En cada cobro, Mercado Pago acredita la comisión a la plataforma y el resto al prestador, en una sola operación.
- La plataforma no custodia el dinero del prestador, lo que simplifica aspectos fiscales y regulatorios.
- Medios: tarjetas, dinero en cuenta, y otros habilitados por Mercado Pago.
- Modalidades: pago total o seña (porcentaje configurable por prestador) con saldo a pagar según política.

**Decidido (noviembre 2026):** cada prestador conecta su cuenta con el botón
"Conectar con Mercado Pago" (OAuth de la aplicación de la plataforma). El pago
entra en su cuenta y Mercado Pago retiene la comisión (más IVA) en el mismo pago
(`marketplace_fee`). Con seña, se retiene como mucho la seña y el resto se
factura aparte. Antes de habilitarlo con plata real: probar con cuentas de
prueba el reparto de las devoluciones. Una credencial pegada a mano sigue
funcionando, pero sin retención.

A evaluar como alternativa o complemento: otras pasarelas locales, y el caso de reservas con varios prestadores (ver Fase 3).

## 9. Arquitectura propuesta

| Capa | Propuesta |
|---|---|
| Frontend | Next.js (web responsive, buena indexación en buscadores) |
| Backend | FastAPI (API REST) |
| Base de datos | PostgreSQL con PostGIS (búsqueda por mapa y distancia) |
| Imágenes | Almacenamiento de objetos con CDN y redimensionado automático |
| Tareas en segundo plano | Cola de trabajos (sincronización iCal, vencimiento de reservas, correos) |
| Notificaciones | Correo y WhatsApp |
| Mapas | Proveedor de mapas con geocodificación |

La API se diseña desde el inicio para ser consumida también por la app móvil (Fase 3).

## 10. Aspectos legales y fiscales a validar

- Términos y condiciones, y política de privacidad (Ley 25.326 de datos personales).
- Obligaciones de defensa del consumidor para ventas en línea (incluida la aplicabilidad del botón de arrepentimiento a servicios turísticos con fecha).
- Facturación de la comisión al prestador ante ARCA.
- Requisitos de habilitación o registro de alojamientos turísticos en cada provincia.
- Rol de la plataforma frente a reclamos entre viajero y prestador.

## 11. Glosario

- **Prestador**: dueño o responsable de un alojamiento o servicio.
- **Publicación**: ficha pública de un alojamiento o servicio.
- **Unidad**: elemento reservable dentro de una publicación.
- **Regla de comisión**: configuración que determina cuánto cobra la plataforma.
- **iCal**: formato estándar para sincronizar calendarios con otras plataformas.

## 12. Preguntas abiertas generales

| Pregunta | Responsable | Bloqueante |
|---|---|---|
| Nombre definitivo y dominio | Dirección | No |
| Política de cancelación estándar y reembolsos | Dirección / Legal | Sí (Fase 1) |
| Facturación de la comisión | Contable | Sí (Fase 1) |
| Pasarela de pago definitiva | Dirección / Técnica | Sí (Fase 1) |
| Idiomas y monedas (¿USD para extranjeros?) | Dirección | No |
