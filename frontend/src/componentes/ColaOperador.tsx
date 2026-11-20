"use client";

import { useState, useTransition } from "react";
import Link from "next/link";

import { accionAprobar, accionRechazar } from "@/lib/acciones-publicaciones";
import type { EnRevision } from "@/lib/api";
import { plural } from "@/lib/formato";
import { Alerta, Rayo } from "./Iconos";
import estilos from "./ColaOperador.module.css";

export default function ColaOperador({ inicial }: { inicial: EnRevision[] }) {
  const [cola, setCola] = useState(inicial);
  const [motivos, setMotivos] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [pendiente, empezar] = useTransition();

  const sacar = (id: string) => setCola((c) => c.filter((p) => p.id !== id));

  if (cola.length === 0) {
    return (
      <p className={estilos.vacio}>
        No hay nada esperando revisión. Cuando un prestador mande una publicación, aparece acá.
      </p>
    );
  }

  return (
    <>
      {error && (
        <p className={estilos.error} role="alert">
          <Alerta className={estilos.icono} />
          {error}
        </p>
      )}
      <ul className={estilos.cola}>
        {cola.map((p) => (
          <li key={p.id} className={estilos.ficha}>
            <div className={estilos.fotos}>
              {p.fotos.slice(0, 4).map((url) => (
                <img key={url} src={url} alt="" loading="lazy" />
              ))}
              {p.fotos.length === 0 && <span className={estilos.sinFotos}>Sin fotos</span>}
            </div>

            <div className={estilos.cuerpo}>
              <h2>{p.titulo}</h2>
              <p className={estilos.meta}>
                {p.localidad} · {p.provincia} — {p.prestador}
                {p.prestador_verificado && (
                  <span className={estilos.verificado}>
                    <Rayo />
                    Prestador verificado
                  </span>
                )}
              </p>
              <p className={estilos.numeros}>
                <span className="cifra">{p.fotos.length}</span> fotos ·{" "}
                <span className="cifra">{p.unidades}</span>{" "}
                {p.unidades === 1 ? "unidad" : "unidades"} · hasta{" "}
                {plural(p.capacidad_maxima, "persona", "personas")}
              </p>
              <p className={estilos.descripcion}>{p.descripcion}</p>

              <div className={estilos.acciones}>
                <Link href={`/alojamiento/${p.slug}`} className={estilos.ver} prefetch={false}>
                  Ver como queda
                </Link>
                <button
                  type="button"
                  className={estilos.aprobar}
                  disabled={pendiente}
                  onClick={() =>
                    empezar(async () => {
                      const r = await accionAprobar(p.id);
                      if (r.error) setError(r.error);
                      else sacar(p.id);
                    })
                  }
                >
                  Aprobar y publicar
                </button>
              </div>

              <details className={estilos.rechazo}>
                <summary>Rechazar</summary>
                <label>
                  <span>Qué tiene que corregir el prestador</span>
                  <textarea
                    rows={2}
                    value={motivos[p.id] ?? ""}
                    onChange={(e) => setMotivos((m) => ({ ...m, [p.id]: e.target.value }))}
                    placeholder="Las fotos no muestran el interior de las unidades."
                  />
                </label>
                <button
                  type="button"
                  disabled={pendiente}
                  onClick={() =>
                    empezar(async () => {
                      const r = await accionRechazar(p.id, motivos[p.id] ?? "");
                      if (r.error) setError(r.error);
                      else sacar(p.id);
                    })
                  }
                >
                  Devolver con este motivo
                </button>
              </details>
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}
