"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import type { Filtros as CatalogoFiltros } from "@/lib/api";
import { pesos } from "@/lib/formato";
import { ICONOS_COMODIDAD, Cruz, Filtro, Rayo } from "./Iconos";
import estilos from "./Filtros.module.css";

export default function Filtros({ catalogo }: { catalogo: CatalogoFiltros }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const dialogo = useRef<HTMLDialogElement>(null);
  const [abierto, setAbierto] = useState(false);

  const subtipos = params.getAll("subtipo");
  const comodidades = params.getAll("comodidad");
  const inmediata = params.get("confirmacion_inmediata") === "true";
  const precioMax = params.get("precio_max") ?? "";
  const orden = params.get("orden") ?? "relevancia";

  const activos =
    subtipos.length + comodidades.length + (inmediata ? 1 : 0) + (precioMax ? 1 : 0);

  useEffect(() => {
    const d = dialogo.current;
    if (!d) return;
    if (abierto && !d.open) d.showModal();
    if (!abierto && d.open) d.close();
  }, [abierto]);

  function navegar(siguiente: URLSearchParams) {
    siguiente.delete("pagina");
    router.push(`${pathname}?${siguiente}`, { scroll: false });
  }

  function alternar(clave: string, valor: string) {
    const siguiente = new URLSearchParams(params);
    const actuales = siguiente.getAll(clave);
    siguiente.delete(clave);
    for (const v of actuales) if (v !== valor) siguiente.append(clave, v);
    if (!actuales.includes(valor)) siguiente.append(clave, valor);
    navegar(siguiente);
  }

  function fijar(clave: string, valor: string | null) {
    const siguiente = new URLSearchParams(params);
    if (valor === null || valor === "") siguiente.delete(clave);
    else siguiente.set(clave, valor);
    navegar(siguiente);
  }

  function limpiar() {
    const siguiente = new URLSearchParams(params);
    for (const clave of ["subtipo", "comodidad", "confirmacion_inmediata", "precio_max", "precio_min"])
      siguiente.delete(clave);
    navegar(siguiente);
  }

  return (
    <div className={estilos.fila}>
      <div className={estilos.chips}>
        <button
          type="button"
          className={`${estilos.chip} ${inmediata ? estilos.activo : ""}`}
          aria-pressed={inmediata}
          onClick={() => fijar("confirmacion_inmediata", inmediata ? null : "true")}
        >
          <Rayo className={estilos.iconoChip} />
          Confirmación inmediata
        </button>

        {catalogo.subtipos.map((s) => {
          const activo = subtipos.includes(s.codigo);
          return (
            <button
              key={s.codigo}
              type="button"
              className={`${estilos.chip} ${activo ? estilos.activo : ""}`}
              aria-pressed={activo}
              onClick={() => alternar("subtipo", s.codigo)}
            >
              {s.nombre}
            </button>
          );
        })}

        <button
          type="button"
          className={`${estilos.chip} ${estilos.mas} ${activos > 0 ? estilos.activo : ""}`}
          onClick={() => setAbierto(true)}
        >
          <Filtro className={estilos.iconoChip} />
          Más filtros
          {activos > 0 && <span className={`${estilos.cuenta} cifra`}>{activos}</span>}
        </button>

        {activos > 0 && (
          <button type="button" className={estilos.limpiar} onClick={limpiar}>
            Limpiar filtros
          </button>
        )}
      </div>

      <label className={estilos.orden}>
        <span>Ordenar por</span>
        <select value={orden} onChange={(e) => fijar("orden", e.target.value)}>
          {catalogo.ordenes.map((o) => (
            <option key={o.codigo} value={o.codigo}>
              {o.nombre}
            </option>
          ))}
        </select>
      </label>

      <dialog ref={dialogo} className={estilos.panel} onClose={() => setAbierto(false)}>
        <header>
          <h2>Filtros</h2>
          <button type="button" onClick={() => setAbierto(false)} aria-label="Cerrar filtros">
            <Cruz />
          </button>
        </header>

        <section>
          <h3>Precio total máximo</h3>
          <p className={estilos.ayuda}>
            Sobre el total de la estadía completa, no por noche.
            {precioMax && <strong> Hasta {pesos(precioMax)}</strong>}
          </p>
          <input
            type="range"
            min={50000}
            max={2000000}
            step={25000}
            value={precioMax || 2000000}
            onChange={(e) =>
              fijar("precio_max", e.target.value === "2000000" ? null : e.target.value)
            }
          />
          <div className={estilos.extremos}>
            <span className="cifra">{pesos(50000)}</span>
            <span className="cifra">{pesos(2000000)}+</span>
          </div>
        </section>

        <section>
          <h3>Servicios</h3>
          <ul className={estilos.comodidades}>
            {catalogo.comodidades.map((c) => {
              const Icono = ICONOS_COMODIDAD[c.codigo];
              const activo = comodidades.includes(c.codigo);
              return (
                <li key={c.codigo}>
                  <button
                    type="button"
                    className={`${estilos.chip} ${activo ? estilos.activo : ""}`}
                    aria-pressed={activo}
                    onClick={() => alternar("comodidad", c.codigo)}
                  >
                    {Icono && <Icono className={estilos.iconoChip} />}
                    {c.nombre}
                  </button>
                </li>
              );
            })}
          </ul>
        </section>

        <footer>
          <button type="button" className={estilos.limpiar} onClick={limpiar}>
            Limpiar todo
          </button>
          <button type="button" className={estilos.aplicar} onClick={() => setAbierto(false)}>
            Ver resultados
          </button>
        </footer>
      </dialog>
    </div>
  );
}
