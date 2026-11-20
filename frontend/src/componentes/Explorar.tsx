import Link from "next/link";

import type { Destino, PaginaExplorar } from "@/lib/api";
import { plural } from "@/lib/formato";
import BotonCercaMio from "./BotonCercaMio";
import Paginado from "./Paginado";
import TarjetaSinFechas from "./TarjetaSinFechas";
import { Ubicacion } from "./Iconos";
import estilos from "./Explorar.module.css";

/** Distancia en km entre dos puntos, para mostrarla en cada tarjeta. */
function km(a: [number, number] | null, lat: number | null, lon: number | null) {
  if (!a || lat == null || lon == null) return null;
  const R = 6371;
  const rad = (g: number) => (g * Math.PI) / 180;
  const dLat = rad(lat - a[0]);
  const dLon = rad(lon - a[1]);
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(rad(a[0])) * Math.cos(rad(lat)) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

/* Lo que ve quien entra a buscar sin haber elegido fechas.

   Antes acá no había nada: un cartel pidiendo fechas y una pantalla en blanco.
   Eso es un callejón —el visitante que todavía no sabe cuándo viaja se va sin
   ver que existe oferta—. Ahora ve lo que hay publicado, y las fechas pasan a
   ser el paso siguiente en vez del peaje de entrada.

   Lo que no hacemos es fingir disponibilidad: sin fechas no se puede saber qué
   está libre, así que el precio es la tarifa base y se dice que lo es. */
export default function Explorar({
  pagina,
  destinos,
  cerca,
}: {
  pagina: PaginaExplorar;
  destinos: Destino[];
  cerca: boolean;
}) {
  const origen = pagina.origen;

  return (
    <div className={estilos.explorar}>
      <div className={estilos.encabezado}>
        <div>
          <h1 className={estilos.titulo}>
            {origen
              ? "Alojamientos cerca tuyo"
              : `${plural(pagina.total, "alojamiento publicado", "alojamientos publicados")}`}
          </h1>
          <p className={estilos.bajada}>
            {origen ? (
              <>
                Ordenados por cercanía.{" "}
                <strong>Elegí las fechas arriba para ver cuáles están libres</strong> y
                cuánto sale en total.
              </>
            ) : (
              <>
                Esto es todo lo que hay, sin filtrar por fechas.{" "}
                <strong>Elegí llegada y salida arriba</strong> para ver cuáles están
                realmente libres y el precio total de tu estadía.
              </>
            )}
          </p>
        </div>
        <BotonCercaMio activo={cerca} />
      </div>

      {destinos.length > 0 && (
        <nav className={estilos.destinos} aria-label="Ir a un destino">
          {destinos.slice(0, 10).map((d) => (
            <Link key={d.slug} href={`/alojamientos-en/${d.slug}`}>
              <Ubicacion className={estilos.pin} />
              {d.nombre}
              <span>{d.publicaciones}</span>
            </Link>
          ))}
        </nav>
      )}

      {pagina.publicaciones.length === 0 ? (
        <p className={estilos.vacio}>Todavía no hay alojamientos publicados.</p>
      ) : (
        <ul className={estilos.grilla}>
          {pagina.publicaciones.map((p) => (
            <li key={p.publicacion_id}>
              <TarjetaSinFechas p={p} km={km(origen, p.lat, p.lon)} />
            </li>
          ))}
        </ul>
      )}

      <Paginado pagina={pagina.pagina} paginas={pagina.paginas} />
    </div>
  );
}
