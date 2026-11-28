import Link from "next/link";

import type { PrimerosPasos as Datos } from "@/lib/api";
import estilos from "./PrimerosPasos.module.css";

/* La lista que lleva al prestador hasta su primera publicación (mejora 3). Qué
   está hecho y qué falta lo calcula el backend con las mismas reglas que el botón
   "Mandar a revisión": acá solo se muestra. */
export default function PrimerosPasos({ datos }: { datos: Datos }) {
  const siguiente = datos.pasos.find((p) => !p.hecho && !p.opcional);
  const porcentaje = datos.total ? Math.round((datos.hechos / datos.total) * 100) : 0;

  return (
    <section className={estilos.panel} aria-labelledby="primeros-pasos">
      <div className={estilos.cabecera}>
        <h2 id="primeros-pasos">Primeros pasos</h2>
        <span className={estilos.cuenta}>
          <span className="cifra">{datos.hechos}</span> de{" "}
          <span className="cifra">{datos.total}</span>
        </span>
      </div>
      <div
        className={estilos.barra}
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={datos.total}
        aria-valuenow={datos.hechos}
        aria-label="Avance"
      >
        <span style={{ width: `${porcentaje}%` }} />
      </div>
      {siguiente && (
        <p className={estilos.siguiente}>
          Lo que sigue: <strong>{siguiente.titulo}</strong>
          {datos.titulo && siguiente.codigo !== "publicacion" ? ` de «${datos.titulo}»` : ""}.
        </p>
      )}

      <ol className={estilos.pasos}>
        {datos.pasos.map((p, i) => {
          const actual = p === siguiente;
          return (
            <li
              key={p.codigo}
              className={`${estilos.paso} ${p.hecho ? estilos.hecho : ""} ${actual ? estilos.actual : ""} ${p.disponible ? "" : estilos.espera}`}
            >
              <span className={estilos.marca} aria-hidden="true">
                {p.hecho ? "✓" : i + 1}
              </span>
              <div className={estilos.texto}>
                <strong>
                  {p.titulo}
                  {p.opcional && <span className={estilos.opcional}>Recomendado</span>}
                </strong>
                <span>{p.detalle}</span>
              </div>
              {p.hecho ? (
                <span className={estilos.listo}>
                  {p.codigo === "revision" ? "En revisión" : "Listo"}
                </span>
              ) : p.disponible ? (
                <Link href={p.enlace} className={actual ? estilos.principal : estilos.secundario}>
                  {p.accion}
                </Link>
              ) : null}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
