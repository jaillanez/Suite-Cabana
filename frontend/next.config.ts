import type { NextConfig } from "next";

/* Dos reenvíos al backend, por el mismo motivo: que el navegador nunca tenga que
   salir del origen del sitio.

   - `/media`: las fotos que sube el prestador las guarda y sirve el backend. En la
     base queda la ruta relativa, que es lo correcto para el día que pasen a un CDN.
   - `/api/v1`: las llamadas que hace el navegador —autocompletado de destinos,
     subir fotos—. Yendo por acá no hay CORS que configurar, y cambiar de dominio o
     de puerto no rompe nada. Lo que pide el servidor va directo, sin este rodeo. */
const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
const DESTINO_API = API.replace(/\/$/, "");
const ORIGEN_API = new URL(API).origin;
const RUTA_API = new URL(API).pathname.replace(/\/$/, "");

const config: NextConfig = {
  async rewrites() {
    return [
      { source: `${RUTA_API}/:ruta*`, destination: `${DESTINO_API}/:ruta*` },
      { source: "/media/:ruta*", destination: `${ORIGEN_API}/media/:ruta*` },
    ];
  },
  output: "standalone",
  // La guía para agentes es la del repo (CLAUDE.md en la raíz); Next no la genera.
  agentRules: false,
  images: { remotePatterns: [] }, // agregar el dominio del CDN de fotos
};

export default config;
