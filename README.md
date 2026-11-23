# Suite Cabaña

Marketplace turístico argentino (nombre público sin definir). Alojamientos, y más adelante
excursiones, gastronomía y traslados, con reserva, pago y comisión configurable.

Especificaciones en [`docs/`](docs/): visión general (00) y fases 1 a 3.
Contexto de producto en [`PRODUCT.md`](PRODUCT.md).

## Stack

| Capa | Tecnología |
|---|---|
| Backend | Python 3.12+, FastAPI, SQLAlchemy 2, Alembic |
| Base de datos | PostgreSQL + PostGIS (local, sin Docker) |
| Frontend | Next.js 16 (App Router, TypeScript), MapLibre GL |
| Pagos | Mercado Pago (modo marketplace) |

## Estructura

```
backend/    API FastAPI, modelos, motor de comisiones y precios, búsqueda, migraciones
frontend/   Web Next.js
scripts/    creación de las bases y descarga de fotos de ejemplo
docs/       PRD por fase
```

## Arranque local

Requiere PostgreSQL con PostGIS corriendo en la máquina:

```bash
brew install postgresql@18 postgis
brew services start postgresql@18
```

Después:

```bash
cp .env.example .env
./scripts/crear_db.sh            # crea suite_cabana y suite_cabana_test con PostGIS

# Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
python -m app.semilla             # catálogo real + oferta de ejemplo
uvicorn app.main:app --reload     # http://localhost:8000/docs

# Frontend
cd ../frontend
npm install
npm run dev                       # http://localhost:3000
```

Si el puerto 8000 o el 3000 están ocupados, levantá el backend en otro
(`uvicorn app.main:app --port 8010`) y apuntá el frontend con
`frontend/.env.local`:

```
NEXT_PUBLIC_API_URL=http://localhost:8010/api/v1
```

## Datos de ejemplo

No hay datos falsos en el código: todo lo que devuelve la API sale de la base. La semilla
la llena mientras no haya prestadores cargando su propia oferta.

La oferta de ejemplo está centrada en la **provincia de San Juan**, con el departamento
**Rivadavia** como foco.

- Provincias, los 19 departamentos de San Juan y sus distritos son **reales**, con
  coordenadas aproximadas de cada cabecera.
- Prestadores, publicaciones, unidades y tarifas son **ficticios** y quedan marcados con
  `es_demo = true` en la base. La pantalla de resultados lo declara.
- Las fotos son reales, de Wikimedia Commons, con licencia libre; el crédito de cada una
  está en `frontend/public/fotos/demo/creditos.json`.
- **Los Búhos** (Médano de Oro, Rawson) es un lugar real y se carga aparte, en
  `app/semilla/datos.py` → `LOS_BUHOS`. Solo lleva los datos verificados; unidades, precios
  y fotos son provisorios y la semilla imprime la lista de faltantes al terminar.

### Las fotos reales de Los Búhos

Van en **`fotos/los-buhos/`** (hay un `LEEME.md` ahí con las instrucciones). Se copian tal
cual salen del teléfono, numeradas —`01-frente.jpg`, `02-pileta.jpg`— porque el orden del
nombre es el orden en la ficha, y la primera es la que se ve en los resultados y al
compartir el enlace.

```bash
python -m app.semilla                     # las toma junto con todo lo demás
python ../scripts/fotos_los_buhos.py      # solo las fotos, sin tocar nada más
python ../scripts/fotos_los_buhos.py --listar   # ver qué encontró y en qué orden
```

Pasan por el mismo procesador que una foto subida desde la web
(`app/services/fotos.py`): WebP, ancho máximo, orientación corregida y **EXIF borrado**.
Lo último importa: la foto de un teléfono lleva adentro la ubicación GPS de dónde se
sacó, y publicarla cruda sería publicar la dirección de la casa. Los originales quedan
intactos en la carpeta, así que volver a sembrar no los pierde.

Nunca se le ponen fotos de banco. El resto de los alojamientos son ficticios y se pueden
ilustrar con cualquier cosa; Los Búhos existe, y ponerle la foto de otra casa sería
tergiversarlo. Mientras no tenga fotos propias, la ficha lo dice.

Las cuentas de ejemplo se pueden usar para entrar y recorrer la aplicación por dentro:
los anfitriones `prestador1@demo.example.com` … `prestador16@demo.example.com` y
`los-buhos@demo.example.com`, y los viajeros `viajero1@demo.example.com` …
`viajero4@demo.example.com`. Todas con la clave **`demo12345`**.

La semilla también crea **reservas de ejemplo**, y las crea con el motor real
(`cotizar → crear → registrar_pago`): quedan con su snapshot de comisión y sus fechas
retenidas igual que en producción. Sin ellas el panel del prestador, los cobros, la cola
del operador y el verde del calendario general no tendrían nada que mostrar. Existen solo si corriste la semilla de ejemplo, y
`--limpiar` se los lleva. (El dominio es `example.com` porque está reservado justamente
para esto: con `.test` el validador de correos rechaza el ingreso.)

```bash
python -m app.semilla                  # catálogo + oferta de ejemplo
python -m app.semilla --solo-catalogo   # solo provincias, localidades, tipos, comodidades
python -m app.semilla --limpiar         # borra la oferta de ejemplo (el catálogo queda)

python ../scripts/fotos_demo.py --cantidad 120   # vuelve a bajar las fotos
```

## Ingreso con Google

El botón solo aparece si hay credencial configurada, y el endpoint responde 501 mientras
no la haya. Para obtenerla:

1. Entrá a [Google Cloud Console](https://console.cloud.google.com/) con tu cuenta de Google
   y creá un proyecto (arriba a la izquierda, "Seleccionar proyecto" → "Proyecto nuevo").
2. En el menú lateral: **APIs y servicios → Pantalla de consentimiento de OAuth**.
   Elegí **Externo**, cargá nombre de la aplicación, tu correo de asistencia y tu correo de
   contacto. Guardá. No hace falta publicarla para probar: alcanza con agregarte como
   **usuario de prueba**.
3. **APIs y servicios → Credenciales → Crear credenciales → ID de cliente de OAuth**.
   Tipo de aplicación: **Aplicación web**.
4. En **Orígenes autorizados de JavaScript** agregá las direcciones desde donde se abre la
   web, sin barra final:
   - `http://localhost:3000`
   - `http://localhost:3001` (si usás ese puerto)
   - más adelante, el dominio de producción.
5. **URI de redireccionamiento autorizados**: dejalo vacío. Se usa el botón de Google
   Identity Services, que devuelve el token en la misma página y no redirige.
6. Copiá el **ID de cliente** (termina en `.apps.googleusercontent.com`) y pegalo en dos
   lugares:

```bash
# .env  (backend)
GOOGLE_CLIENT_ID=123456789-abcdef.apps.googleusercontent.com

# frontend/.env.local
NEXT_PUBLIC_GOOGLE_CLIENT_ID=123456789-abcdef.apps.googleusercontent.com
```

Reiniciá el backend y el frontend. El **secreto de cliente** que Google también muestra no
se usa acá: con el botón de Identity Services alcanza el ID, y por eso el ID puede estar en
el frontend sin riesgo.

El backend verifica la firma del token contra las claves públicas de Google y comprueba que
el destinatario sea este `GOOGLE_CLIENT_ID`: un token emitido para otra aplicación se
rechaza. Si el correo ya tiene cuenta con contraseña, se vincula en vez de duplicarla.

## Cómo habla el navegador con la API

El servidor (componentes de servidor y acciones) llama al backend **directo**, a
`NEXT_PUBLIC_API_URL`. El navegador, en cambio, pide siempre a la misma dirección del
sitio y Next lo reenvía (`next.config.ts`): `/api/v1/*` y `/media/*`.

No es un rodeo gratuito. Llamando directo al origen de la API desde el navegador hay que
listar en CORS cada dominio y cada puerto del frontend, y el día que cambia alguno lo
único que se rompe son las llamadas del navegador —el autocompletado de destinos, subir
fotos—. Se rompen **en silencio**, porque el resto de la página la arma el servidor y
sigue andando. Yendo por el mismo origen no hay CORS que mantener.

## Formas de pago

El producto **no se ata a una billetera**. Todo el sistema habla con la interfaz
`app/services/pagos/base.py` y nunca con una pasarela directamente: agregar una es escribir
un adaptador y registrarlo en `app/services/pagos/__init__.py`, sin tocar reservas,
comisiones ni pantallas.

| Billetera | Estado |
|---|---|
| **Pago simulado** | Funciona. Solo en entorno local: permite recorrer reservar → pagar → confirmada sin credenciales de nadie. |
| **Mercado Pago** | Adaptador completo, en modo marketplace: la comisión se acredita a la plataforma y el resto al prestador en la misma operación. Falta cargar `MP_ACCESS_TOKEN`. |
| MODO · Ualá · Cuenta DNI · Naranja X · PayPal | **Previstas**: tienen su lugar, sus credenciales en `.env` y su registro. El adaptador se escribe cuando tengamos la documentación técnica de cada una. |

Las previstas figuran a propósito en `GET /api/v1/pasarelas`, cada una diciendo qué le
falta. Es preferible a un adaptador inventado que falle recién en producción, contra dinero
real.

Para agregar una: escribir una clase que cumpla `Pasarela` (crear preferencia, validar la
firma de la notificación, traducirla a un estado nuestro, y reintegrar), sumarla al registro,
y cargar sus credenciales en `.env`.

## Calendario integrado con otras plataformas

El anfitrión que ya vende en Airbnb y en Booking no puede estar copiando fechas a mano.
`/mi-calendario` muestra **todas sus unidades en una sola grilla** —días en columnas— con
lo vendido acá, lo importado de los otros portales y lo que bloqueó él, y un botón que los
trae a todos de una. Si un portal está caído, los demás igual se actualizan.

La sincronización es **iCal (RFC 5545)** y va en las dos direcciones: la dirección de ellos
se pega en el editor de la unidad, la nuestra se pega en el panel de ellos.

| Plataforma | Estado |
|---|---|
| **Airbnb** | Funciona. Calendario del anuncio → Disponibilidad → Sincronizar calendarios. |
| **Booking.com** | Funciona para departamentos y casas. Extranet → Tarifas y disponibilidad → Sincronizar calendarios. Si la propiedad está cargada como hotel con channel manager, va por ahí. |
| **Vrbo / Expedia** | Funciona. Panel del anuncio → Calendario → Importar y exportar. |
| **Google Calendar** | Funciona. Sirve para bloquear fechas del calendario propio. |
| Cualquier otro portal con `.ics` | Funciona, aunque no esté en la lista. |
| **Despegar** | **No se puede todavía.** Su extranet tiene calendario, pero no publica un iCal que el anfitrión pueda copiar: hace falta su API de partners o un channel manager en el medio. Hasta entonces, lo vendido ahí se bloquea a mano. |

El catálogo vive en `app/services/canales.py` y lo sirve `GET /api/v1/canales`, con las
instrucciones de cada una. La plataforma se detecta sola por el dominio de la URL.

### Despegar y las ventas propias: por mail, no por scraping

Despegar no da iCal, pero manda un mail de confirmación por cada reserva. Eso alcanza:
`/mi-calendario` tiene una bandeja donde el mail se convierte en reserva y bloquea las
fechas, que después salen hacia Airbnb y Booking por el iCal que exportamos. Lo mismo
sirve para la venta cerrada por WhatsApp o por teléfono, que se carga a mano. Ninguna de
las dos genera comisión: no las vendimos nosotros.

Hay dos formas de que el mail entre:

| | |
|---|---|
| **Pegarlo a mano** | Funciona hoy, sin contratar nada. `POST /api/v1/mi-calendario/correo`. |
| **Reenvío automático** | Cada anfitrión tiene una dirección propia (`reservas+<id>@…`). Pone una regla de reenvío y las reservas entran solas. Necesita un proveedor de correo entrante (SendGrid Inbound Parse, Mailgun Routes, Postmark) y las tres variables `CORREO_ENTRANTE_*`. Sin `CORREO_ENTRANTE_SECRETO` el endpoint responde 503 a propósito: un buzón abierto al mundo deja que cualquiera te ocupe el calendario. |

**Por qué reenvío y no scraping de la extranet.** Entrar a Despegar con un navegador
headless era posible, pero exigía guardar el usuario y la contraseña de la extranet de
cada anfitrión —la misma credencial que sirve para cancelar reservas y ver datos de
huéspedes—, rompía en silencio cada vez que cambiaran el HTML, y arriesgaba que les
suspendieran la cuenta por acceso automatizado. El reenvío no nos da acceso a nada más
que a los mensajes que el anfitrión elige mandarnos, y cuando falla, falla ruidosamente.

**Lo que no se entiende, no bloquea.** El análisis (`app/services/correo/analisis.py`) lee
fechas, huésped, código, personas y monto; las fechas argentinas van día primero, siempre.
Si algo falta —o si el mail no dice a qué unidad va y el anfitrión tiene varias— la reserva
queda en «por revisar» y no toca el calendario hasta que él la complete. Un calendario que
se calla cuando no entendió es exactamente cómo se vende dos veces la misma noche.

**Dos límites que conviene tener claros**, porque ninguna plataforma los resuelve:

- iCal transmite **solo qué noches están ocupadas**. No lleva precios, ni datos del
  huésped, ni el detalle de la reserva.
- **No es en tiempo real**: cada portal relee los calendarios ajenos cada una a cuatro
  horas. Dos ventas simultáneas en portales distintos siguen siendo posibles. Por eso la
  garantía dura de cero dobles reservas vive en la restricción de exclusión de nuestra
  base, no en la sincronización.

## Comisión

Cuánto cobra la plataforma y quién lo paga es **configuración, no código**. La regla por
defecto se cambia sin tocar la aplicación:

```bash
python -m app.semilla comision --porcentaje 10 --quien-paga prestador   # la absorbe el prestador
python -m app.semilla comision --porcentaje 10 --quien-paga viajero     # cargo de servicio visible
python -m app.semilla comision --porcentaje 10 --quien-paga dividido --porcentaje-viajero 50
python -m app.semilla comision --porcentaje 0                           # sin comisión
```

El desglose de precio siempre nombra el cargo de servicio, aunque valga cero: cambiar la
regla no obliga a cambiar la pantalla. Reglas más específicas (por provincia, temporada,
prestador, monto) se cargan como `regla_comision` y ganan por especificidad; ver `docs/00 §7`
y el simulador en `POST /api/v1/comisiones/simular`.

## Estado

Bloques **1 a 7 cerrados** del plan de Fase 1 (`docs/01 §8`):

- Base técnica, modelo de datos completo con migraciones, catálogos reales.
- Cuentas y roles: registro, ingreso, sesión con JWT en cookie httpOnly, verificación de
  correo, y alta de prestador con sus datos fiscales. Un usuario puede ser viajero y
  prestador a la vez. Las dos reglas de R1 están aplicadas: sin correo verificado no se
  reserva, y sin datos fiscales más cuenta de cobro no se publica.
- Motor de comisiones con snapshot, tests y simulador.
- Motor de precios (temporadas, día de la semana, cargos, descuentos) con tests.
- Búsqueda real: `GET /api/v1/publicaciones/buscar` con disponibilidad verificada contra
  bloqueos y calendarios externos, distancia por PostGIS, filtros, orden y paginado.
- Ficha de publicación: `GET /api/v1/publicaciones/{slug}`, con disponibilidad y precio por
  unidad cuando hay fechas, y tarifa base cuando no las hay.
- Alta de publicaciones por el prestador: editor con datos, ubicación en mapa, servicios,
  fotos (se optimizan y convierten a WebP al subirlas), unidades y tarifas por temporada.
  Estados borrador → en revisión → aprobada / rechazada, más pausar y reactivar.
- Aprobación por el operador, con motivo obligatorio al devolver una publicación.
- Calendario: bloqueo manual de fechas, e importación y exportación iCal para sincronizar
  con Booking y Airbnb. Un calendario ajeno nunca pisa una reserva propia: se importa solo
  lo que queda libre y lo demás se informa.
- Calendario integrado: `/mi-calendario` junta todas las unidades del anfitrión en una
  grilla única, con el origen de cada bloqueo, y trae todos los portales de una sola vez.
  Ver «Calendario integrado con otras plataformas» más arriba.
- Paneles: favoritos del viajero, cobros y comisiones del prestador, y control del operador
  con filtros y exportación a CSV.
- Notificaciones: buzón de salida con correo (por consola en desarrollo, SMTP cuando esté
  configurado) y WhatsApp previsto. Toda notificación se guarda antes de enviarse.
- Términos y condiciones y política de privacidad, aceptados al registrarse y al reservar,
  con la versión guardada en cada caso.
- Reservas y pagos: retención de fechas mientras se paga, snapshot de comisión por reserva,
  webhooks idempotentes, confirmación inmediata o por solicitud del prestador, cancelación
  con reintegro según la política que la reserva guardó, y liberación automática de las
  reservas no pagadas.
- Páginas por destino para buscadores, con `sitemap.xml` y `robots.txt`.
- Pantallas: `/`, `/buscar`, `/alojamiento/[slug]`, `/alojamientos-en/[localidad]`,
  `/publicar`, `/mi-calendario` y el 404. 25 rutas en total.

Falta para cerrar la Fase 1:

- **Bloque 8** — lanzamiento controlado con los prestadores iniciales, y los ajustes que
  salgan de esa prueba.

Y estas piezas de los bloques anteriores, que dependen de decisiones o credenciales de
afuera del código:

| Qué falta | De quién depende |
|---|---|
| Credenciales de Mercado Pago y de las otras billeteras | Dirección |
| `GOOGLE_CLIENT_ID` para el ingreso con Google | Técnica |
| Servidor de correo (SMTP) | Técnica |
| Proveedor de WhatsApp | Dirección (`docs/01 §9`) |
| Revisión legal de términos y privacidad | Legal (`docs/00 §10`) |
| Porcentajes de las políticas de cancelación | Dirección (`docs/01 §9`) |
| Comisión por defecto y quién la paga | Dirección (`docs/01 §9`) |
| Cola de trabajos para tareas periódicas | Técnica (`docs/00 §9`) |

**Mensajería interna** entre viajero y prestador, **reseñas** y **reclamos** están marcados
como P1 y P2 en `docs/01 §5` y quedan fuera de la Fase 1.

Pendientes conocidos dentro de lo ya construido:

- **Verificación por teléfono**: falta decidir el proveedor de WhatsApp (`docs/01 §9`).
- **WhatsApp**: los avisos se guardan en el buzón marcados como descartados, con el motivo.
  El día que haya proveedor se pueden reenviar, en vez de haberse perdido.
- **Comisión retenida en el pago**: con cobro directo (credencial propia del anfitrión)
  Mercado Pago no deja retenerla; se factura aparte. Retenerla requiere OAuth de
  marketplace (`docs/00 §8`).
- **Sincronización automática de calendarios**: hoy es a pedido, con un botón. Puede
  sumarse a `app/tareas.py`, que ya corre cada minuto.
- **Fotos**: se guardan en disco (`backend/media/`, servido por el backend y reenviado por
  Next). `docs/00 §9` prevé almacenamiento de objetos con CDN; cambia `app/services/fotos.py`
  y nada más, porque en la base se guarda la ruta relativa.
- **Copias de seguridad** de la base de producción: sin configurar.

Ya resueltos: envío de correos (verificación por SMTP), vinculación de Mercado Pago por
el anfitrión, liberación de reservas vencidas y envío de notificaciones
(`app/tareas.py`).

Salones de eventos y paquete salón + cabañas: hechos
([`docs/04-salones-de-eventos.md`](docs/04-salones-de-eventos.md)). Falta la etapa 7,
cargar el salón real de Los Búhos con sus datos y fotos.

## Producción (alojateaqui.com.ar)

Corre en el VPS compartido, en `/opt/suite-cabana`, con el repo clonado en
`/opt/suite-cabana/app`. Base, red y volúmenes propios; ningún puerto en el host.
Solo el contenedor web entra a la red del Caddy de entrada (`suite-turnos_edge`).

```bash
git push                                        # el servidor baja de GitHub
ssh root@173.212.195.122 /opt/suite-cabana/app/deploy/deploy.sh
```

`deploy/deploy.sh` genera una sola vez los secretos en `/opt/suite-cabana/.env`
(`POSTGRES_PASSWORD`, `SECRET_KEY`, `CLAVE_CIFRADO`), aplica migraciones, carga el
catálogo la primera vez y agrega el dominio al Caddy de entrada con copia previa.
**`CLAVE_CIFRADO` no se puede perder ni cambiar**: cifra las credenciales de
Mercado Pago de los anfitriones, y sin ella tendrían que volver a cargarlas.

Cobros: `MP_COBRO_DIRECTO=true`. Cada anfitrión pega su Access Token en *Mi cuenta*
y lo que le reservan entra en su cuenta de Mercado Pago. Con credencial propia
Mercado Pago no permite retener la comisión en el mismo pago: queda registrada en
cada reserva (*Cobros y comisiones*) y se factura aparte al anfitrión.

## Tests

```bash
cd backend && pytest        # los de búsqueda necesitan suite_cabana_test
ruff check .
```

```bash
cd frontend && npx tsc --noEmit && npm run build
```

Nuevas migraciones: `alembic revision --autogenerate -m "..."`.
