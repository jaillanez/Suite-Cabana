"use client";

/* Si falla el diseño entero (no solo una página), Next reemplaza todo el
   documento: por eso lleva su propio <html> y estilos mínimos en línea. */

export default function ErrorGlobal() {
  return (
    <html lang="es-AR">
      <body style={{ fontFamily: "system-ui, sans-serif", padding: "6rem 1.5rem", maxWidth: 480, margin: "0 auto" }}>
        <h1 style={{ fontSize: "1.75rem" }}>No pudimos mostrar esta página</h1>
        <p style={{ color: "#555" }}>
          Puede que hayamos actualizado el sitio mientras lo usabas. Recargá la página para seguir:
          lo que ya habías guardado está a salvo.
        </p>
        <button type="button" onClick={() => window.location.reload()} style={{ padding: "0.7rem 1.1rem", marginTop: "0.75rem" }}>
          Recargar la página
        </button>
      </body>
    </html>
  );
}
