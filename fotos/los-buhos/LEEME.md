# Fotos reales de Los Búhos

Copiá acá las fotos **tal cual salen del teléfono o la cámara**. No hace falta
recortarlas, achicarlas ni convertirlas: de eso se encarga el sistema.

```
fotos/los-buhos/
  01-frente.jpg
  02-pileta.jpg
  03-cabana-1-interior.jpg
  ...
```

**El orden es el del nombre del archivo**, así que numeralas: `01-`, `02-`, `03-`.
La primera es la que se ve en los resultados de búsqueda y al compartir el enlace,
así que poné adelante la mejor foto del lugar completo.

Sirven `.jpg`, `.jpeg`, `.png`, `.webp` y `.heic` si tu Mac ya las convierte.

## Para que entren

```bash
cd backend
.venv/bin/python -m app.semilla          # las toma junto con todo lo demás
# o, para cargar solo las fotos sin tocar nada más:
.venv/bin/python ../scripts/fotos_los_buhos.py
```

## Qué les hace el sistema

Pasan por el mismo procesamiento que cuando un anfitrión sube una foto desde la
web (`backend/app/services/fotos.py`):

- Se convierten a **WebP** y se achican a un ancho máximo, para que la página cargue
  rápido en el celular de quien busca.
- Se corrige la orientación, que si no la mitad sale acostada.
- **Se les borra el EXIF.** Es importante: las fotos del teléfono llevan adentro la
  ubicación GPS exacta de dónde se sacaron. Publicarlas crudas sería publicar la
  dirección de la casa.

El original tuyo no se toca: queda en esta carpeta.

## Un aviso

Mientras Los Búhos siga con datos provisorios (unidades, precios, dirección exacta),
la publicación queda marcada como ejemplo. Poner las fotos reales es un paso; la
lista completa de lo que falta la imprime la semilla al terminar.
