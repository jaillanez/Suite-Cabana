import type { MetadataRoute } from "next";

const SITIO = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      // La búsqueda con fechas genera infinitas combinaciones sin valor para indexar.
      disallow: "/buscar",
    },
    sitemap: `${SITIO}/sitemap.xml`,
  };
}
