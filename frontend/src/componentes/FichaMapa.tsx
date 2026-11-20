"use client";

import type { Resultado } from "@/lib/api";
import { useSearchParams } from "next/navigation";

import { pesos, plural } from "@/lib/formato";
import { Cruz, Rayo } from "./Iconos";
import estilos from "./FichaMapa.module.css";

/* Tocar un pin tiene que mostrar algo. En la vista de mapa la lista no está, así
   que la ficha compacta aparece sobre el mapa, como en cualquier buscador de la
   categoría. */
export default function FichaMapa({
  resultado: r,
  noches,
  onCerrar,
}: {
  resultado: Resultado;
  noches: number;
  onCerrar: () => void;
}) {
  const parametros = useSearchParams();
  const consulta = new URLSearchParams();
  for (const clave of ["desde", "hasta", "personas", "mascotas"]) {
    const valor = parametros.get(clave);
    if (valor) consulta.set(clave, valor);
  }

  return (
    <article className={estilos.ficha}>
      <a
        href={`/alojamiento/${r.slug}${consulta.size ? `?${consulta}` : ""}`}
        className={estilos.enlace}
      >
        {r.fotos[0] ? (
          <img src={r.fotos[0].url} alt="" className={estilos.foto} loading="lazy" />
        ) : (
          <span className={`${estilos.foto} ${estilos.sinFoto}`} />
        )}
        <div className={estilos.cuerpo}>
          <h3>{r.titulo}</h3>
          <p className={estilos.detalle}>
            {r.unidad.nombre} · hasta {plural(r.unidad.capacidad, "persona", "personas")}
          </p>
          {r.confirmacion_inmediata && (
            <p className={estilos.inmediata}>
              <Rayo />
              Confirmación inmediata
            </p>
          )}
          <p className={`${estilos.precio} cifra`}>{pesos(r.unidad.precio.total)}</p>
          <p className={estilos.leyenda}>total por {plural(noches, "noche", "noches")}</p>
        </div>
      </a>
      <button type="button" onClick={onCerrar} aria-label="Cerrar" className={estilos.cerrar}>
        <Cruz />
      </button>
    </article>
  );
}
