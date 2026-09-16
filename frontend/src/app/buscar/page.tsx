type Props = { searchParams: Promise<Record<string, string | undefined>> };

// Bloque 4 del plan (docs/01 §8): resultados en lista y mapa desde la API.
export default async function Buscar({ searchParams }: Props) {
  const { destino, desde, hasta, personas } = await searchParams;
  return (
    <main style={{ padding: "2rem 1.5rem" }}>
      <h1>Alojamientos en {destino}</h1>
      <p>
        Del {desde} al {hasta}, {personas} personas. Todavía no hay resultados: la búsqueda se
        conecta en el bloque 4.
      </p>
    </main>
  );
}
