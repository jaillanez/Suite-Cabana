import type { NextConfig } from "next";

const config: NextConfig = {
  output: "standalone",
  images: { remotePatterns: [] }, // agregar el dominio del CDN de fotos
};

export default config;
