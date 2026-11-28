"use client";

/* Cuando una página se rompe. El caso más común no es un error nuestro: alguien
   tenía la página abierta desde antes de un despliegue y su botón llama a una
   acción que ya no existe. Recargar lo resuelve, y lo ya guardado sigue ahí. */

import Link from "next/link";

import estilos from "./no-encontrado.module.css";

const ACTUALIZACION = /Server Action|older or newer deployment|ChunkLoadError|Loading chunk/i;

export default function ErrorDePagina({ error }: { error: Error & { digest?: string } }) {
  const actualizado = ACTUALIZACION.test(error.message ?? "");
  return (
    <main className={estilos.pagina}>
      <p className={estilos.codigo}>{actualizado ? "Sitio actualizado" : "Algo falló"}</p>
      <h1>{actualizado ? "Actualizamos el sitio mientras lo usabas" : "No pudimos mostrar esta página"}</h1>
      <p className={estilos.cuerpo}>
        {actualizado
          ? "Recargá la página para seguir. Lo que ya habías guardado está a salvo; el último cambio, si no se vio guardado, hacelo de nuevo."
          : "Probá recargarla. Si vuelve a pasar, avisanos y contanos qué estabas haciendo."}
      </p>
      <button type="button" className={estilos.accion} onClick={() => window.location.reload()}>
        Recargar la página
      </button>
      <Link href="/">Ir al inicio</Link>
    </main>
  );
}
