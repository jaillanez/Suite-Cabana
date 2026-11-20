import estilos from "./cargando.module.css";

/* Esqueleto con la forma real de las tarjetas: la página no salta cuando llegan
   los datos. */
export default function Cargando() {
  return (
    <div className={estilos.pagina} aria-busy="true" aria-live="polite">
      <span className={estilos.oculto}>Buscando alojamientos disponibles…</span>
      <div className={estilos.encabezado}>
        <span className={estilos.lineaAncha} />
        <span className={estilos.lineaAngosta} />
      </div>
      <div className={estilos.grilla}>
        {Array.from({ length: 6 }, (_, i) => (
          <div key={i} className={estilos.tarjeta}>
            <span className={estilos.foto} />
            <span className={estilos.lineaAncha} />
            <span className={estilos.lineaAngosta} />
            <span className={estilos.precio} />
          </div>
        ))}
      </div>
    </div>
  );
}
