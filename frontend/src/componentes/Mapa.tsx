"use client";

import { useEffect, useRef } from "react";
import maplibregl, { type Map as MapaGL, type Marker } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import type { Resultado } from "@/lib/api";
import { pesos } from "@/lib/formato";
import estilos from "./Mapa.module.css";

/* Teselas de OpenStreetMap: sin clave ni costo, con la atribución que exige la
   licencia. Para producción hay que pasar a un proveedor con cuota propia
   (docs/00 §9 lo deja como decisión abierta). */
const ESTILO: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      maxzoom: 19,
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    },
  },
  layers: [{ id: "osm", type: "raster", source: "osm" }],
};

type Props = {
  resultados: Resultado[];
  centro: { lat: number | null; lon: number | null };
  activa: string | null;
  onActivar: (id: string | null) => void;
  /** En vista de mapa la lista no está en pantalla: el pin no tiene a dónde saltar. */
  fijarSeleccion?: boolean;
};

export default function Mapa({
  resultados,
  centro,
  activa,
  onActivar,
  fijarSeleccion = false,
}: Props) {
  const contenedor = useRef<HTMLDivElement>(null);
  const mapa = useRef<MapaGL | null>(null);
  const marcas = useRef<Map<string, Marker>>(new Map());
  const alActivar = useRef(onActivar);
  alActivar.current = onActivar;
  const soloSeleccionar = useRef(fijarSeleccion);
  soloSeleccionar.current = fijarSeleccion;

  useEffect(() => {
    if (!contenedor.current || mapa.current) return;
    mapa.current = new maplibregl.Map({
      container: contenedor.current,
      style: ESTILO,
      center: [centro.lon ?? -64, centro.lat ?? -38],
      zoom: centro.lat ? 11 : 4,
      attributionControl: { compact: true },
    });
    mapa.current.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    mapa.current.keyboard.enable();
    return () => {
      mapa.current?.remove();
      mapa.current = null;
    };
  }, [centro.lat, centro.lon]);

  useEffect(() => {
    const m = mapa.current;
    if (!m) return;

    for (const marca of marcas.current.values()) marca.remove();
    marcas.current.clear();

    const conUbicacion = resultados.filter((r) => r.lat !== null && r.lon !== null);
    for (const r of conUbicacion) {
      const el = document.createElement("button");
      el.type = "button";
      el.className = estilos.pin;
      el.textContent = pesos(r.unidad.precio.total);
      el.setAttribute("aria-label", `${r.titulo}, ${pesos(r.unidad.precio.total)} en total`);
      el.addEventListener("mouseenter", () => {
        if (!soloSeleccionar.current) alActivar.current(r.publicacion_id);
      });
      el.addEventListener("mouseleave", () => {
        if (!soloSeleccionar.current) alActivar.current(null);
      });
      el.addEventListener("click", () => {
        alActivar.current(r.publicacion_id);
        if (soloSeleccionar.current) return; // la ficha aparece sobre el mapa
        document
          .getElementById(`ficha-${r.publicacion_id}`)
          ?.scrollIntoView({ behavior: "smooth", block: "center" });
      });
      marcas.current.set(
        r.publicacion_id,
        new maplibregl.Marker({ element: el }).setLngLat([r.lon!, r.lat!]).addTo(m),
      );
    }

    if (conUbicacion.length > 1) {
      const limites = new maplibregl.LngLatBounds();
      for (const r of conUbicacion) limites.extend([r.lon!, r.lat!]);
      m.fitBounds(limites, { padding: 56, maxZoom: 14, duration: 0 });
    } else if (conUbicacion.length === 1) {
      m.setCenter([conUbicacion[0].lon!, conUbicacion[0].lat!]);
      m.setZoom(13);
    }
  }, [resultados]);

  useEffect(() => {
    for (const [id, marca] of marcas.current) {
      marca.getElement().classList.toggle(estilos.activo, id === activa);
    }
  }, [activa]);

  return (
    <div className={estilos.marco}>
      <div ref={contenedor} className={estilos.mapa} />
      {resultados.length === 0 && (
        <p className={estilos.aviso}>No hay alojamientos para mostrar en el mapa</p>
      )}
    </div>
  );
}
