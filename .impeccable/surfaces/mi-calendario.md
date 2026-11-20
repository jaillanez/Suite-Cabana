# Superficie: `/mi-calendario`

**Modo:** Operate. El anfitrión entra a responder una pregunta: *¿qué noches tengo
tomadas, en todas mis unidades, vengan de donde vengan?* Sale habiendo conectado un
calendario o habiendo detectado un choque.

## Qué tiene que pasar en los primeros tres segundos

Ver la grilla completa —unidades en filas, días en columnas— y entender sin leer
nada que hay tres clases de ocupación: la que nos deja plata, la que viene de otro
portal y la que cerró el anfitrión.

## Decisiones

- **Verde = venta nuestra.** La regla «un solo verde» del sistema acá gana
  significado: el acento marca reservas hechas en Suite Cabaña. Lo importado de
  Airbnb o Booking va en gris sólido, lo bloqueado a mano en rayado neutro. El color
  no decora, informa de dónde viene el dinero.
- **Tabla de verdad, no divs.** Es una grilla de datos: `<table>` con `th` de fila
  pegajoso. Da semántica, navegación por teclado y encabezados gratis.
- **Scroll horizontal contenido.** 60 días no entran en 1440px. Scrollea la grilla,
  nunca la página; la columna de unidades queda fija.
- **Un botón que sincroniza todo.** Que un portal esté caído no puede frenar a los
  otros: el resultado se informa fila por fila.
- **Despegar figura, con el motivo.** No publica iCal para el anfitrión. Decirlo es
  más útil que esconderlo: hasta que haya API de partners, esas fechas se bloquean
  a mano.

## Fuera de alcance

Editar tramos desde acá (eso vive en el editor de cada unidad) y precios por día.

## Segunda entrega: las ventas que entran por fuera

Despegar no publica iCal y una venta por WhatsApp no tiene calendario ninguno. La
pantalla suma una sección donde las dos entran: pegando el mail de confirmación o
cargándolas a mano.

- **Nada se bloquea adivinando.** Si el análisis no entendió algo —o si el mail no
  dice a qué unidad va y hay doce— la reserva cae en una bandeja roja que declara
  qué falta y **no toca el calendario**. Confirmar es un clic, pero es del
  anfitrión.
- **La bandeja va arriba del formulario.** Lo que está a medias es más urgente que
  cargar algo nuevo: si aparece, es lo primero que se ve.
- **Solapas y no dos formularios.** «Pegar el mail» y «Cargarla a mano» compiten
  por el mismo espacio y nunca se usan juntas.
- **El verde no cambia de significado.** Una venta de afuera es gris rayado como
  todo lo que no vendimos nosotros. El acento sigue siendo plata nuestra.
