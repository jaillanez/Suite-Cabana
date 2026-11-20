import Link from "next/link";

import type { Destino } from "@/lib/api";
import { rangoFechas } from "@/lib/formato";
import { Lupa, Ubicacion } from "./Iconos";
import estilos from "./SinResultados.module.css";

type Props = {
  motivo: "sin-fechas" | "sin-disponibilidad" | "destino-desconocido" | "error";
  destino?: string;
  desde?: string;
  hasta?: string;
  sugerencias?: Destino[];
  mensaje?: string;
};

const TEXTOS = {
  "sin-fechas": {
    titulo: "Elegí las fechas de tu viaje",
    cuerpo: "Sin fechas no podemos saber qué está realmente libre. Cargá llegada y salida arriba.",
  },
  "sin-disponibilidad": {
    titulo: "No hay lugar para esas fechas",
    cuerpo:
      "Hay alojamientos en este destino, pero ninguno está libre en el rango que pediste, o no entra esa cantidad de personas.",
  },
  "destino-desconocido": {
    titulo: "Todavía no conocemos ese destino",
    cuerpo: "Puede que aún no tengamos alojamientos publicados ahí. Estos son los que sí tienen:",
  },
  error: {
    titulo: "No pudimos traer los resultados",
    cuerpo: "Puede ser un problema momentáneo de conexión. Probá de nuevo en un momento.",
  },
} as const;

export default function SinResultados({
  motivo,
  destino,
  desde,
  hasta,
  sugerencias = [],
  mensaje,
}: Props) {
  const texto = TEXTOS[motivo];
  return (
    <section className={estilos.caja}>
      <span className={estilos.marca} aria-hidden="true">
        <Lupa />
      </span>
      <h2>{texto.titulo}</h2>
      <p className={estilos.cuerpo}>{mensaje ?? texto.cuerpo}</p>

      {motivo === "sin-disponibilidad" && destino && desde && hasta && (
        <p className={estilos.detalle}>
          Buscaste en <strong>{destino}</strong>, {rangoFechas(desde, hasta)}. Probá corriendo las
          fechas unos días, bajando la cantidad de personas o sacando filtros.
        </p>
      )}

      {sugerencias.length > 0 && (
        <ul className={estilos.sugerencias}>
          {sugerencias.map((d) => (
            <li key={d.slug}>
              <Link href={`/buscar?localidad=${d.slug}${desde ? `&desde=${desde}` : ""}${hasta ? `&hasta=${hasta}` : ""}`}>
                <Ubicacion className={estilos.icono} />
                <span>
                  <strong>{d.nombre}</strong>
                  <span className={estilos.provincia}>{d.provincia}</span>
                </span>
                <span className={`${estilos.cuenta} cifra`}>{d.publicaciones}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
