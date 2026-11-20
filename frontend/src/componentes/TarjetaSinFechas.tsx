import Link from "next/link";

import type { ResumenDestino } from "@/lib/api";
import { distanciaCorta, pesos, plural } from "@/lib/formato";
import { ICONOS_COMODIDAD, Rayo } from "@/componentes/Iconos";
import estilos from "./TarjetaSinFechas.module.css";

/* La tarjeta de un alojamiento cuando todavía no hay fechas: muestra qué hay,
   no qué está libre. Por eso el precio es «tarifa base» y nunca un total —un
   total sin fechas sería un número inventado. */
export default function TarjetaSinFechas({
  p,
  km,
}: {
  p: ResumenDestino;
  km?: number | null;
}) {
  return (
    <article className={estilos.tarjeta}>
      <Link href={`/alojamiento/${p.slug}`} className={estilos.foto}>
        {p.fotos[0] ? (
          <img src={p.fotos[0].url} alt={`${p.titulo}, foto principal`} loading="lazy" />
        ) : (
          <span className={estilos.sinFoto}>Sin fotos</span>
        )}
      </Link>
      <div className={estilos.cuerpo}>
        <h3>
          <Link href={`/alojamiento/${p.slug}`}>{p.titulo}</Link>
        </h3>
        <p className={estilos.detalle}>
          {[p.subtipo, p.zona ?? p.localidad].filter(Boolean).join(" · ")}
          {km != null && <span className={estilos.km}> · a {distanciaCorta(km)}</span>}
        </p>
        <p className={estilos.detalle}>
          Hasta {plural(p.capacidad_maxima, "persona", "personas")}
        </p>
        {p.confirmacion_inmediata && (
          <p className={estilos.inmediata}>
            <Rayo />
            Confirmación inmediata
          </p>
        )}
        {p.comodidades.length > 0 && (
          <ul className={estilos.comodidades}>
            {p.comodidades.slice(0, 5).map((codigo) => {
              const Icono = ICONOS_COMODIDAD[codigo];
              return Icono ? (
                <li key={codigo}>
                  <Icono className={estilos.iconoChico} />
                </li>
              ) : null;
            })}
          </ul>
        )}
        {p.tarifa_desde && (
          <p className={estilos.tarifa}>
            <span className="cifra">{pesos(p.tarifa_desde)}</span> tarifa base por noche
          </p>
        )}
      </div>
    </article>
  );
}
