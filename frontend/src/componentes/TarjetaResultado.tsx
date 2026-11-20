"use client";

import { useSearchParams } from "next/navigation";

import type { Resultado } from "@/lib/api";
import { distancia, pesos, pesosExactos, plural } from "@/lib/formato";
import BotonFavorito from "./BotonFavorito";
import GaleriaTarjeta from "./GaleriaTarjeta";
import { ICONOS_COMODIDAD, Personas, Rayo } from "./Iconos";
import estilos from "./TarjetaResultado.module.css";

type Props = {
  resultado: Resultado;
  noches: number;
  /** Códigos de comodidad → nombre, para que los íconos no queden mudos. */
  nombresComodidad?: Record<string, string>;
  /** Vínculo con el mapa: la tarjeta y su pin se resaltan juntos. */
  favorito?: boolean;
  activa?: boolean;
  onEntrar?: (id: string) => void;
  onSalir?: () => void;
};

export default function TarjetaResultado({
  resultado: r,
  noches,
  nombresComodidad = {},
  favorito = false,
  activa = false,
  onEntrar,
  onSalir,
}: Props) {
  const parametros = useSearchParams();
  // La ficha tiene que abrirse con las mismas fechas: si no, el viajero pierde
  // lo que ya eligió y vuelve a ver "elegí las fechas".
  const consulta = new URLSearchParams();
  for (const clave of ["desde", "hasta", "personas", "mascotas"]) {
    const valor = parametros.get(clave);
    if (valor) consulta.set(clave, valor);
  }
  const enlace = `/alojamiento/${r.slug}${consulta.size ? `?${consulta}` : ""}`;

  const p = r.unidad.precio;
  const hayCargo = Number(p.cargo_servicio) > 0;
  const hayDescuento = Number(p.descuento) > 0;
  const lejania = distancia(r.distancia_km);

  return (
    <article
      id={`ficha-${r.publicacion_id}`}
      className={`${estilos.tarjeta} ${activa ? estilos.activa : ""}`}
      onMouseEnter={() => onEntrar?.(r.publicacion_id)}
      onMouseLeave={() => onSalir?.()}
      onFocus={() => onEntrar?.(r.publicacion_id)}
      onBlur={() => onSalir?.()}
    >
      <div className={estilos.foto}>
        <GaleriaTarjeta fotos={r.fotos} titulo={r.titulo} />
        <BotonFavorito publicacionId={r.publicacion_id} inicial={favorito} />
      </div>

      <div className={estilos.cuerpo}>
        <div className={estilos.encabezado}>
          <h3 className={estilos.titulo}>
            {/* El enlace cubre la tarjeta entera; los controles que van encima
                suben de capa para seguir siendo clickeables. */}
            <a href={enlace} className={estilos.enlace}>
              {r.titulo}
            </a>
          </h3>
          {r.confirmacion_inmediata && (
            <span className={estilos.inmediata}>
              <Rayo />
              Confirmación inmediata
            </span>
          )}
        </div>

        <p className={estilos.ubicacion}>
          {[r.subtipo, r.localidad, r.provincia].filter(Boolean).join(" · ")}
        </p>
        {lejania && <p className={estilos.distancia}>{lejania}</p>}

        <p className={estilos.unidad}>
          <Personas className={estilos.iconoChico} />
          <span>
            {r.unidad.nombre} · hasta {plural(r.unidad.capacidad, "persona", "personas")}
          </span>
          {r.unidades_disponibles > 1 && (
            <span className={estilos.otras}>
              +{r.unidades_disponibles - 1}{" "}
              {r.unidades_disponibles === 2 ? "unidad más" : "unidades más"}
            </span>
          )}
        </p>

        {r.comodidades.length > 0 && (
          <ul className={estilos.comodidades}>
            {r.comodidades.slice(0, 5).map((codigo) => {
              const Icono = ICONOS_COMODIDAD[codigo];
              const nombre = nombresComodidad[codigo];
              return Icono && nombre ? (
                <li key={codigo} title={nombre}>
                  <Icono className={estilos.iconoChico} titulo={nombre} />
                </li>
              ) : null;
            })}
          </ul>
        )}

        <div className={estilos.precio}>
          <p className={`${estilos.total} cifra`}>{pesos(p.total)}</p>
          <p className={estilos.leyenda}>
            total por {plural(noches, "noche", "noches")}
            {hayDescuento && <span className={estilos.descuento}>−{pesos(p.descuento)}</span>}
          </p>
          <details className={estilos.desglose}>
            <summary>Ver desglose</summary>
            <dl>
              <div>
                <dt>
                  {plural(p.noches, "noche", "noches")} a {pesos(p.promedio_noche)}
                </dt>
                <dd className="cifra">{pesosExactos(p.alojamiento)}</dd>
              </div>
              {hayDescuento && (
                <div className={estilos.resta}>
                  <dt>Descuento por estadía ({Number(p.porcentaje_descuento)}%)</dt>
                  <dd className="cifra">−{pesosExactos(p.descuento)}</dd>
                </div>
              )}
              {Number(p.limpieza) > 0 && (
                <div>
                  <dt>Limpieza</dt>
                  <dd className="cifra">{pesosExactos(p.limpieza)}</dd>
                </div>
              )}
              {Number(p.personas_extra) > 0 && (
                <div>
                  <dt>Personas adicionales</dt>
                  <dd className="cifra">{pesosExactos(p.personas_extra)}</dd>
                </div>
              )}
              {Number(p.mascotas) > 0 && (
                <div>
                  <dt>Mascotas</dt>
                  <dd className="cifra">{pesosExactos(p.mascotas)}</dd>
                </div>
              )}
              {hayCargo && (
                <div>
                  <dt>Cargo de servicio</dt>
                  <dd className="cifra">{pesosExactos(p.cargo_servicio)}</dd>
                </div>
              )}
              <div className={estilos.totalFila}>
                <dt>Total</dt>
                <dd className="cifra">{pesosExactos(p.total)}</dd>
              </div>
            </dl>
            <p className={estilos.nota}>
              {hayCargo
                ? "El cargo de servicio ya está incluido en el total."
                : "Sin cargos adicionales: este es el precio final."}
            </p>
          </details>
        </div>
      </div>
    </article>
  );
}
