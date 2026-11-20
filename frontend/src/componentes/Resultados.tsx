"use client";

import dynamic from "next/dynamic";
import { useState } from "react";

import type { Busqueda } from "@/lib/api";
import FichaMapa from "./FichaMapa";
import { Lista, Mapa as IconoMapa } from "./Iconos";
import TarjetaResultado from "./TarjetaResultado";
import estilos from "./Resultados.module.css";

const Mapa = dynamic(() => import("./Mapa"), {
  ssr: false,
  loading: () => <div className={estilos.mapaCargando} />,
});

type Props = {
  busqueda: Busqueda;
  /** Título, aviso y filtros viven dentro de la columna de la lista, para que el
      mapa arranque arriba de todo y entre entero en el primer pantallazo. */
  encabezado?: React.ReactNode;
  pie?: React.ReactNode;
  nombresComodidad?: Record<string, string>;
  favoritos?: string[];
};

export default function Resultados({
  busqueda,
  encabezado,
  pie,
  nombresComodidad,
  favoritos = [],
}: Props) {
  const [activa, setActiva] = useState<string | null>(null);
  const [vista, setVista] = useState<"lista" | "mapa">("lista");
  const enMapa = vista === "mapa";
  const activo = busqueda.resultados.find((r) => r.publicacion_id === activa) ?? null;

  return (
    <div className={`${estilos.contenedor} ${enMapa ? estilos.vistaMapa : estilos.vistaLista}`}>
      <div className={estilos.columna}>
        {encabezado}
        <ul className={estilos.lista}>
          {busqueda.resultados.map((r) => (
            <li key={r.publicacion_id}>
              <TarjetaResultado
                resultado={r}
                noches={busqueda.noches}
                nombresComodidad={nombresComodidad}
                favorito={favoritos.includes(r.publicacion_id)}
                activa={activa === r.publicacion_id}
                onEntrar={setActiva}
                onSalir={() => setActiva(null)}
              />
            </li>
          ))}
        </ul>
        {pie}
      </div>

      <aside className={estilos.mapa}>
        <Mapa
          resultados={busqueda.resultados}
          centro={busqueda.destino}
          activa={activa}
          onActivar={setActiva}
          fijarSeleccion={enMapa}
        />
        {enMapa && activo && (
          <FichaMapa
            resultado={activo}
            noches={busqueda.noches}
            onCerrar={() => setActiva(null)}
          />
        )}
      </aside>

      <button
        type="button"
        className={estilos.alternar}
        onClick={() => {
          setActiva(null);
          setVista((v) => (v === "lista" ? "mapa" : "lista"));
        }}
      >
        {enMapa ? <Lista /> : <IconoMapa />}
        {enMapa ? "Ver lista" : "Ver mapa"}
      </button>
    </div>
  );
}
