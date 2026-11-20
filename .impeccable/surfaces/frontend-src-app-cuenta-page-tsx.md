---
version: 1
slug: "frontend-src-app-cuenta-page-tsx"
primary_target: "frontend/src/app/cuenta/page.tsx"
related_targets: ["frontend/src/app/ingresar/page.tsx","frontend/src/app/registrarse/page.tsx"]
---

# Cuenta y sesión — `/cuenta`, `/ingresar`, `/registrarse`, `/verificar-email`

**Modo:** Operate. Trámite, no persuasión.

**Audiencia y trabajo:** alguien que ya decidió usar el producto y necesita una cuenta para reservar, o un prestador que viene a cargar sus datos fiscales. Nadie llega acá a mirar.

**Acción primaria:** entrar o crear la cuenta en la menor cantidad de campos posible, y después entender qué falta para poder operar.

**Restricciones:** el token vive en una cookie httpOnly; el JavaScript de la página nunca lo ve. Sin correo verificado no se puede reservar, y sin datos fiscales más cuenta de cobro no se puede publicar: las dos cosas se dicen en la pantalla, no se descubren al chocar.

## Direction contract

**THESIS:** La pantalla de cuenta dice qué falta y por qué importa, en el momento en que falta. Rechaza el panel que muestra un estado "incompleto" sin explicar qué se pierde, y rechaza el formulario que descubre sus reglas recién al enviarlo.

**OWN-WORLD:** Superficie derivada, sin mundo propio: el sistema documentado en DESIGN.md. Formularios de campo etiquetado sobre fondo claro, un solo acento verde en la acción de enviar, el par ámbar reservado a lo que está pendiente y el acento tenue a lo que ya está resuelto.

**STORY:** El visitante crea su cuenta en cinco campos, ve inmediatamente que le falta verificar el correo y qué le impide eso, lo resuelve, y si quiere publicar entiende que necesita CUIT y cuenta de cobro antes de intentarlo.

**FIRST VIEWPORT:** En ingreso y registro, una columna angosta centrada: título, una línea de contexto, los campos y un solo botón. En cuenta, el saludo con el cierre de sesión enfrentado, y debajo tres bloques separados por línea: datos, verificación y publicación, cada uno con su estado explícito.

**FORM:** El estándar de la categoría, la decisión registrada en PRODUCT.md. Superficie utilitaria dentro de un mundo ya establecido: hereda, no inventa.

**FINISH:** unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance.
