---
version: 1
slug: "frontend-src-app-reservas-codigo-page-tsx"
primary_target: "frontend/src/app/reservas/[codigo]/page.tsx"
related_targets: ["frontend/src/app/reservas/page.tsx","frontend/src/app/mis-reservas/page.tsx"]
---

# Reservas y pago — `/reservas`, `/reservas/[codigo]`, `/mis-reservas`

**Modo:** Operate. Es el momento en que se mueve plata: ninguna duda puede quedar sin responder en la pantalla.

**Audiencia y trabajo:** el viajero que ya decidió y ahora paga, y después vuelve a mirar su reserva. Y el prestador que recibe una solicitud y decide.

**Acción primaria:** pagar. Después, entender el estado y poder cancelar sabiendo cuánto se devuelve.

**Prueba disponible:** el desglose exacto que se cobró, la política que el viajero aceptó, el reintegro calculado para hoy, y qué billeteras se pueden usar. Para el prestador: cuánto le queda después de la comisión.

**Restricciones:** el importe mostrado es el snapshot de la reserva, no un recálculo. Las billeteras que no se pueden usar se muestran con el motivo, nunca ocultas.

## Direction contract

**THESIS:** La pantalla de pago que no esconde nada: el desglose completo antes de pagar, la política de cancelación con el número de hoy, y la lista honesta de con qué se puede y con qué no. Rechaza el checkout que revela el total recién en la pasarela, y rechaza la grilla de logos de billeteras que no están habilitadas.

**OWN-WORLD:** El sistema documentado en DESIGN.md. El total en el peso más alto, cifras tabulares, el acento verde solo en la acción que avanza, el par ámbar para lo que está esperando y el rojo para lo cancelado.

**STORY:** El viajero ve qué reservó, cuánto paga y por qué, elige billetera, paga, y la pantalla le dice en qué estado quedó y qué pasa si cancela. El prestador ve la solicitud con lo que le queda limpio y decide.

**FIRST VIEWPORT:** El alojamiento y el código de reserva enfrentados. Debajo el estado con su explicación en una línea. Después la estadía, el total con su desglose, y la acción de pagar.

**FORM:** El estándar de la categoría, la decisión registrada en PRODUCT.md. Superficie dentro de un mundo establecido: hereda.

**FINISH:** unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance.
