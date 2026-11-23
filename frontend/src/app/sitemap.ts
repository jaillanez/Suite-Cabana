import type { MetadataRoute } from "next";

import { buscarSalones, destino, destinos } from "@/lib/api";

const SITIO = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

/* Las páginas por destino y las fichas son las que tienen que indexarse
   (docs/01 §5 R4). La búsqueda con fechas no: cambia todo el tiempo. */
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const fijas: MetadataRoute.Sitemap = [
    { url: `${SITIO}/`, changeFrequency: "daily", priority: 1 },
    { url: `${SITIO}/publicar`, changeFrequency: "monthly", priority: 0.5 },
  ];

  const lugares = await destinos().catch(() => []);
  const paginasDestino: MetadataRoute.Sitemap = lugares.map((d) => ({
    url: `${SITIO}/alojamientos-en/${d.slug}`,
    changeFrequency: "daily",
    priority: 0.8,
  }));

  const fichas = await Promise.all(
    lugares.map((d) =>
      destino(d.slug, new URLSearchParams({ por_pagina: "48" }))
        .then((p) => p.publicaciones.map((x) => x.slug))
        .catch(() => [] as string[]),
    ),
  );

  // Los salones (docs/04): la búsqueda sin día es estable, se puede indexar.
  const salones = await buscarSalones(new URLSearchParams({ por_pagina: "48" }))
    .then((r) => r.resultados.map((s) => s.slug))
    .catch(() => [] as string[]);

  return [
    ...fijas,
    {
      url: `${SITIO}/salones`,
      changeFrequency: "daily" as const,
      priority: 0.8,
    },
    ...salones.map((slug) => ({
      url: `${SITIO}/salon/${slug}`,
      changeFrequency: "weekly" as const,
      priority: 0.7,
    })),
    ...paginasDestino,
    ...fichas.flat().map((slug) => ({
      url: `${SITIO}/alojamiento/${slug}`,
      changeFrequency: "weekly" as const,
      priority: 0.7,
    })),
  ];
}
