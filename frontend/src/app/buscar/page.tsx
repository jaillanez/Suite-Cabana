import type { Metadata } from "next";

import {
  ApiError,
  buscar,
  destinos as traerDestinos,
  explorar,
  filtrosDisponibles,
  misFavoritos,
  type Destino,
} from "@/lib/api";
import { tokenActual } from "@/lib/sesion";
import { legible, plural, rangoFechas } from "@/lib/formato";
import AvisoDemo from "@/componentes/AvisoDemo";
import BarraBusqueda from "@/componentes/BarraBusqueda";
import Explorar from "@/componentes/Explorar";
import Filtros from "@/componentes/Filtros";
import Marca from "@/componentes/Marca";
import MenuCuenta from "@/componentes/MenuCuenta";
import Paginado from "@/componentes/Paginado";
import Resultados from "@/componentes/Resultados";
import SinResultados from "@/componentes/SinResultados";
import estilos from "./buscar.module.css";

type Params = Record<string, string | string[] | undefined>;
type Props = { searchParams: Promise<Params> };

const PASAN = [
  "localidad",
  "provincia",
  "lat",
  "lon",
  "radio_km",
  "desde",
  "hasta",
  "personas",
  "mascotas",
  "precio_min",
  "precio_max",
  "subtipo",
  "comodidad",
  "confirmacion_inmediata",
  "orden",
  "pagina",
] as const;

function aParametros(params: Params): URLSearchParams {
  const salida = new URLSearchParams();
  for (const clave of PASAN) {
    const valor = params[clave];
    if (valor === undefined) continue;
    for (const v of Array.isArray(valor) ? valor : [valor]) if (v !== "") salida.append(clave, v);
  }
  return salida;
}

export async function generateMetadata({ searchParams }: Props): Promise<Metadata> {
  const params = await searchParams;
  const destino = typeof params.localidad === "string" ? legible(params.localidad) : null;
  return {
    title: destino ? `Alojamientos en ${destino}` : "Buscar alojamiento",
    description: destino
      ? `Alojamientos disponibles en ${destino} con precio total y reserva en línea.`
      : "Buscá alojamiento por destino, fechas y cantidad de personas.",
  };
}

export default async function Buscar({ searchParams }: Props) {
  const params = await searchParams;
  const consulta = aParametros(params);
  const desde = consulta.get("desde");
  const hasta = consulta.get("hasta");
  const slug = consulta.get("localidad");
  const personas = Number(consulta.get("personas") ?? 2);

  const conservar = Object.fromEntries(
    PASAN.filter((c) => !["localidad", "desde", "hasta", "personas", "pagina"].includes(c))
      .map((c) => [c, consulta.getAll(c)])
      .filter(([, v]) => (v as string[]).length > 0),
  ) as Record<string, string[]>;

  /* El nombre que muestra la barra tiene que ser el mismo que el del título: el
     slug de la URL es un identificador, no un destino. */
  const encabezado = (nombre?: string | null) => (
    <header className={estilos.barra}>
      <div className={estilos.barraInterna}>
        <Marca compacta />
        <BarraBusqueda
          valores={{
            localidad: slug ?? undefined,
            localidadNombre: nombre ?? (slug ? legible(slug) : undefined),
            desde: desde ?? undefined,
            hasta: hasta ?? undefined,
            personas,
          }}
          variante="compacta"
          conservar={conservar}
        />
        <MenuCuenta compacto />
      </div>
    </header>
  );

  /* Sin fechas no se puede saber qué está libre, pero sí qué hay. Mandar al
     visitante a una pantalla en blanco hasta que cargue un calendario es
     perderlo antes de que vea que existe oferta. */
  if (!desde || !hasta) {
    const paraExplorar = new URLSearchParams();
    for (const clave of ["localidad", "provincia", "lat", "lon", "personas", "subtipo",
                         "comodidad", "pagina"] as const) {
      for (const v of consulta.getAll(clave)) paraExplorar.append(clave, v);
    }
    const [vista, lugares] = await Promise.all([
      explorar(paraExplorar).catch(() => null),
      traerDestinos().catch(() => [] as Destino[]),
    ]);
    return (
      <>
        {encabezado()}
        <main className={estilos.pagina} id="resultados">
          <AvisoDemo />
          {vista ? (
            <Explorar
              pagina={vista}
              destinos={lugares}
              cerca={Boolean(consulta.get("lat") && consulta.get("lon"))}
            />
          ) : (
            <SinResultados motivo="sin-fechas" />
          )}
        </main>
      </>
    );
  }

  const token = await tokenActual();
  const [resultado, catalogo, guardados] = await Promise.allSettled([
    buscar(consulta),
    filtrosDisponibles(),
    token ? misFavoritos(token) : Promise.resolve([]),
  ]);

  if (resultado.status === "rejected") {
    const e = resultado.reason;
    const esDestino = e instanceof ApiError && e.status === 404;
    const sugerencias =
      e instanceof ApiError && e.detalle && typeof e.detalle === "object"
        ? (((e.detalle as { sugerencias?: Destino[] }).sugerencias ?? []) as Destino[])
        : [];
    return (
      <>
        {encabezado()}
        <main className={estilos.pagina} id="resultados">
          <AvisoDemo />
          <SinResultados
            motivo={esDestino ? "destino-desconocido" : "error"}
            desde={desde}
            hasta={hasta}
            sugerencias={sugerencias}
            mensaje={
              !esDestino && e instanceof ApiError && e.status === 422 ? e.message : undefined
            }
          />
        </main>
      </>
    );
  }

  const busqueda = resultado.value;
  const lugar = busqueda.destino.localidad ?? busqueda.destino.provincia ?? "todo el país";
  const nombresComodidad = Object.fromEntries(
    catalogo.status === "fulfilled"
      ? catalogo.value.comodidades.map((c) => [c.codigo, c.nombre])
      : [],
  );

  const resumen = (
    <div className={estilos.cabecera}>
      <div className={estilos.resumen}>
        <h1 className={estilos.titulo}>
          {busqueda.total === 0
            ? `Sin lugar en ${lugar}`
            : `${plural(busqueda.total, "alojamiento", "alojamientos")} en ${lugar}`}
        </h1>
        <p className={estilos.contexto}>
          {rangoFechas(desde, hasta)} · {plural(busqueda.noches, "noche", "noches")} ·{" "}
          {plural(personas, "persona", "personas")} · precios totales en pesos
        </p>
      </div>
      <AvisoDemo />
      {catalogo.status === "fulfilled" && <Filtros catalogo={catalogo.value} />}
    </div>
  );

  return (
    <>
      {encabezado(busqueda.destino.localidad)}
      <main className={estilos.pagina} id="resultados">
        {busqueda.total === 0 ? (
          <>
            {resumen}
            <SinResultados
              motivo="sin-disponibilidad"
              destino={lugar}
              desde={desde}
              hasta={hasta}
            />
          </>
        ) : (
          <Resultados
            busqueda={busqueda}
            encabezado={resumen}
            nombresComodidad={nombresComodidad}
            favoritos={
              guardados.status === "fulfilled"
                ? guardados.value.map((f) => f.publicacion_id)
                : []
            }
            pie={<Paginado pagina={busqueda.pagina} paginas={busqueda.paginas} />}
          />
        )}
      </main>
    </>
  );
}
