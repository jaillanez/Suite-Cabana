"use client";

import { useEffect, useRef } from "react";
import maplibregl, { type Map as MapaGL, type Marker } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import estilos from "./MapaSelector.module.css";

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

/* Marcar la ubicación escribiendo coordenadas es pedirle al prestador algo que no
   tiene. Se arrastra el pin o se toca el mapa. */
export default function MapaSelector({
  lat,
  lon,
  onMover,
  ayuda = "Tocá el mapa o arrastrá el pin hasta la puerta del alojamiento.",
}: {
  lat: number | null;
  lon: number | null;
  onMover: (lat: number, lon: number) => void;
  ayuda?: string;
}) {
  const contenedor = useRef<HTMLDivElement>(null);
  const mapa = useRef<MapaGL | null>(null);
  const marca = useRef<Marker | null>(null);
  const alMover = useRef(onMover);
  alMover.current = onMover;

  useEffect(() => {
    if (!contenedor.current || mapa.current) return;
    const centro: [number, number] = [lon ?? -68.58, lat ?? -31.53];
    mapa.current = new maplibregl.Map({
      container: contenedor.current,
      style: ESTILO,
      center: centro,
      zoom: lat ? 14 : 11,
      attributionControl: { compact: true },
    });
    mapa.current.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

    const el = document.createElement("div");
    el.className = estilos.pin;
    marca.current = new maplibregl.Marker({ element: el, draggable: true })
      .setLngLat(centro)
      .addTo(mapa.current);
    marca.current.on("dragend", () => {
      const p = marca.current!.getLngLat();
      alMover.current(Number(p.lat.toFixed(6)), Number(p.lng.toFixed(6)));
    });
    mapa.current.on("click", (e) => {
      marca.current?.setLngLat(e.lngLat);
      alMover.current(Number(e.lngLat.lat.toFixed(6)), Number(e.lngLat.lng.toFixed(6)));
    });

    return () => {
      mapa.current?.remove();
      mapa.current = null;
    };
    // Solo al montar: después el pin se mueve solo, no se reconstruye el mapa.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Si el punto llega de afuera (lo ubicó el backend por la dirección), el pin y
  // el mapa van ahí. Un punto que puso el mismo pin no se mueve: ya está.
  useEffect(() => {
    if (lat === null || lon === null || !marca.current || !mapa.current) return;
    const actual = marca.current.getLngLat();
    if (Math.abs(actual.lat - lat) < 1e-6 && Math.abs(actual.lng - lon) < 1e-6) return;
    marca.current.setLngLat([lon, lat]);
    // Salto directo: volar desde el centro por defecto puede cruzar el país y tardar.
    mapa.current.jumpTo({ center: [lon, lat], zoom: Math.max(mapa.current.getZoom(), 15) });
  }, [lat, lon]);

  return (
    <div className={estilos.marco}>
      <div ref={contenedor} className={estilos.mapa} />
      <p className={estilos.ayuda}>
        {ayuda}
        {lat !== null && lon !== null && (
          <span className="cifra">
            {" "}
            {lat.toFixed(5)}, {lon.toFixed(5)}
          </span>
        )}
      </p>
    </div>
  );
}
