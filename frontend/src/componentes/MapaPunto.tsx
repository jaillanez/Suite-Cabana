"use client";

import { useEffect, useRef } from "react";
import maplibregl, { type Map as MapaGL } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import estilos from "./MapaPunto.module.css";

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

export default function MapaPunto({
  lat,
  lon,
  etiqueta,
}: {
  lat: number;
  lon: number;
  etiqueta: string;
}) {
  const contenedor = useRef<HTMLDivElement>(null);
  const mapa = useRef<MapaGL | null>(null);

  useEffect(() => {
    if (!contenedor.current || mapa.current) return;
    mapa.current = new maplibregl.Map({
      container: contenedor.current,
      style: ESTILO,
      center: [lon, lat],
      zoom: 13,
      attributionControl: { compact: true },
    });
    mapa.current.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

    const el = document.createElement("div");
    el.className = estilos.pin;
    el.setAttribute("aria-label", etiqueta);
    new maplibregl.Marker({ element: el }).setLngLat([lon, lat]).addTo(mapa.current);

    return () => {
      mapa.current?.remove();
      mapa.current = null;
    };
  }, [lat, lon, etiqueta]);

  return <div ref={contenedor} className={estilos.mapa} />;
}
