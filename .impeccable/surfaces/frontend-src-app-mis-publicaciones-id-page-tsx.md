---
version: 1
slug: "frontend-src-app-mis-publicaciones-id-page-tsx"
primary_target: "frontend/src/app/mis-publicaciones/[id]/page.tsx"
related_targets: ["frontend/src/app/mis-publicaciones/page.tsx","frontend/src/app/admin/publicaciones/page.tsx"]
---

# Alta de publicaciones — `/mis-publicaciones`, `/mis-publicaciones/[id]`, `/admin/publicaciones`

**Modo:** Operate. Trabajo, no vidriera.

**Audiencia y trabajo:** el prestador, que no es una persona técnica y muchas veces carga desde el teléfono, armando una publicación en varias sesiones. Y el operador, que revisa una cola y decide.

**Acción primaria:** para el prestador, dejar la publicación en condiciones de mandarse a revisión. Para el operador, aprobar o devolver con un motivo entendible.

**Prueba disponible:** la lista de faltantes que calcula el backend, el estado real de la publicación, y lo que el prestador ya cargó. Nada se infiere en la pantalla.

**Restricciones:** la validación de completitud vive en `app/services/edicion.py` y llega calculada; la pantalla la muestra, no la duplica. En revisión, la publicación se bloquea para edición. Sin cuenta de cobro vinculada no se puede mandar a revisión.

## Direction contract

**THESIS:** El editor que dice qué falta antes de que lo intentes, y todo junto. Rechaza el formulario largo que valida al enviar y devuelve un error por vez, y rechaza el estado "incompleto" que no explica qué le falta.

**OWN-WORLD:** El sistema documentado en DESIGN.md. Bloques con borde de 1px como separadores, un solo acento verde en la acción que avanza, el par ámbar para lo pendiente y el rojo solo para lo que se rechazó. Sin mundo nuevo.

**STORY:** El prestador crea un borrador con dos datos, ve una lista clara de lo que falta, la va tachando a su ritmo, y cuando queda vacía el botón de mandar a revisión se habilita solo. El operador ve la publicación como quedaría y decide en un gesto.

**FIRST VIEWPORT:** Nombre de la publicación con su estado al lado y la acción que corresponde a ese estado. Debajo, en ámbar, lo que falta, enumerado. Después los bloques en orden de trabajo: datos, mapa, servicios, fotos, unidades. En la cola del operador: los contadores arriba y cada publicación con sus fotos a la izquierda y la decisión a la derecha.

**FORM:** El estándar de la categoría, la decisión registrada en PRODUCT.md. Superficie de trabajo dentro de un mundo ya establecido: hereda, no inventa.

**FINISH:** unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance.
