"use client";

import { useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import type { Ficha } from "@/lib/api";
import { hoyISO, pesos, pesosExactos, plural } from "@/lib/formato";
import BotonReservar from "./BotonReservar";
import { Personas, Rayo } from "./Iconos";
import estilos from "./PanelReserva.module.css";

export default function PanelReserva({ ficha }: { ficha: Ficha }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();

  const desde = params.get("desde") ?? "";
  const hasta = params.get("hasta") ?? "";
  const personas = Number(params.get("personas") ?? 2);
  const conFechas = ficha.noches !== null;

  const disponibles = ficha.unidades.filter((u) => u.disponible);
  const [elegidaId, setElegidaId] = useState<string | null>(null);
  const elegida =
    ficha.unidades.find((u) => u.id === elegidaId) ?? disponibles[0] ?? ficha.unidades[0] ?? null;

  function fijar(cambios: Record<string, string>) {
    const siguiente = new URLSearchParams(params);
    for (const [clave, valor] of Object.entries(cambios)) {
      if (valor) siguiente.set(clave, valor);
      else siguiente.delete(clave);
    }
    router.replace(`${pathname}?${siguiente}`, { scroll: false });
  }

  const precio = elegida?.precio ?? null;

  return (
    <aside className={estilos.panel}>
      <div className={estilos.fechas}>
        <label>
          <span>Llegada</span>
          <input
            type="date"
            value={desde}
            min={hoyISO()}
            onChange={(e) =>
              fijar({ desde: e.target.value, ...(hasta <= e.target.value ? { hasta: "" } : {}) })
            }
          />
        </label>
        <label>
          <span>Salida</span>
          <input
            type="date"
            value={hasta}
            min={desde || hoyISO()}
            onChange={(e) => fijar({ hasta: e.target.value })}
          />
        </label>
        <label className={estilos.personas}>
          <span>Personas</span>
          <div className={estilos.conIcono}>
            <Personas className={estilos.icono} />
            <select value={personas} onChange={(e) => fijar({ personas: e.target.value })}>
              {Array.from({ length: 12 }, (_, i) => i + 1).map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </div>
        </label>
      </div>

      {!conFechas && (
        <p className={estilos.aviso}>
          Elegí las fechas para ver qué unidades están libres y cuánto sale en total.
        </p>
      )}

      <ul className={estilos.unidades}>
        {ficha.unidades.map((u) => {
          const elegible = u.disponible !== false;
          const seleccionada = elegida?.id === u.id;
          return (
            <li key={u.id}>
              <button
                type="button"
                className={`${estilos.unidad} ${seleccionada ? estilos.seleccionada : ""} ${
                  elegible ? "" : estilos.ocupada
                }`}
                onClick={() => elegible && setElegidaId(u.id)}
                aria-pressed={seleccionada}
                disabled={!elegible}
              >
                <span className={estilos.nombre}>{u.nombre}</span>
                <span className={estilos.capacidad}>
                  hasta {plural(u.capacidad, "persona", "personas")}
                  {u.estadia_minima > 1 && ` · mínimo ${u.estadia_minima} noches`}
                </span>
                {u.precio ? (
                  <span className={`${estilos.monto} cifra`}>{pesos(u.precio.total)}</span>
                ) : u.disponible === false ? (
                  <span className={estilos.motivo}>{u.motivo}</span>
                ) : (
                  <span className={estilos.base}>
                    <span className="cifra">{u.tarifa_base ? pesos(u.tarifa_base) : "—"}</span> por
                    noche
                  </span>
                )}
              </button>
            </li>
          );
        })}
      </ul>

      {precio && elegida && (
        <div className={estilos.desglose}>
          <p className={`${estilos.total} cifra`}>{pesos(precio.total)}</p>
          <p className={estilos.leyenda}>
            total por {plural(precio.noches, "noche", "noches")} en {elegida.nombre}
          </p>
          <dl>
            <div>
              <dt>
                {plural(precio.noches, "noche", "noches")} a {pesos(precio.promedio_noche)}
              </dt>
              <dd className="cifra">{pesosExactos(precio.alojamiento)}</dd>
            </div>
            {Number(precio.descuento) > 0 && (
              <div className={estilos.resta}>
                <dt>Descuento por estadía ({Number(precio.porcentaje_descuento)}%)</dt>
                <dd className="cifra">−{pesosExactos(precio.descuento)}</dd>
              </div>
            )}
            {Number(precio.limpieza) > 0 && (
              <div>
                <dt>Limpieza</dt>
                <dd className="cifra">{pesosExactos(precio.limpieza)}</dd>
              </div>
            )}
            {Number(precio.personas_extra) > 0 && (
              <div>
                <dt>Personas adicionales</dt>
                <dd className="cifra">{pesosExactos(precio.personas_extra)}</dd>
              </div>
            )}
            {Number(precio.mascotas) > 0 && (
              <div>
                <dt>Mascotas</dt>
                <dd className="cifra">{pesosExactos(precio.mascotas)}</dd>
              </div>
            )}
            {Number(precio.cargo_servicio) > 0 && (
              <div>
                <dt>Cargo de servicio</dt>
                <dd className="cifra">{pesosExactos(precio.cargo_servicio)}</dd>
              </div>
            )}
            <div className={estilos.totalFila}>
              <dt>Total</dt>
              <dd className="cifra">{pesosExactos(precio.total)}</dd>
            </div>
          </dl>
        </div>
      )}

      {conFechas && disponibles.length === 0 && (
        <p className={estilos.sinLugar}>
          No hay unidades libres para esas fechas. Probá corriendo el rango unos días.
        </p>
      )}

      {elegida && precio && desde && hasta ? (
        <BotonReservar
          unidadId={elegida.id}
          desde={desde}
          hasta={hasta}
          adultos={personas}
          etiqueta={ficha.confirmacion_inmediata ? "Reservar" : "Solicitar reserva"}
        />
      ) : (
        <button type="button" className={estilos.reservar} disabled>
          {conFechas ? "Elegí una unidad disponible" : "Elegí las fechas"}
        </button>
      )}
      <p className={estilos.nota}>
        Te guardamos las fechas mientras pagás. Si no completás el pago, se liberan solas.
      </p>

      {ficha.confirmacion_inmediata && (
        <p className={estilos.inmediata}>
          <Rayo />
          Confirmación inmediata: no hay que esperar la respuesta del prestador.
        </p>
      )}
    </aside>
  );
}
