"use client";

/* Un traslado en el detalle de la reserva (docs/06): la ida y, si hay, la vuelta,
   con los datos del viaje. El viajero corrige el vuelo y las notas de los viajes
   que no salieron; las direcciones no, porque el precio por km salió de ahí. */

import { Fragment, useState, useTransition } from "react";

import { accionCambiarViaje } from "@/lib/acciones-reservas";
import type { ItemReserva, Reserva } from "@/lib/api";
import { diaAR, horaAR, pesosExactos, plural } from "@/lib/formato";
import estilos from "./DetalleReserva.module.css";

type Desglose = {
  sentido?: string;
  origen?: string;
  destino?: string;
  km?: string | null;
  valijas?: number;
  lineas?: { concepto: string; monto: string }[];
};

const desglose = (i: ItemReserva) => i.desglose as Desglose;

/** Un traslado guarda el sentido de cada viaje en el desglose. */
export const esTraslado = (r: Reserva) =>
  typeof (r.items[0]?.desglose as Desglose | undefined)?.sentido === "string";

/* La ida primero: los ítems llegan ordenados por el principal, que es el primero en salir. */
const viajes = (r: Reserva) =>
  [...r.items].sort((a, b) => (a.inicio_en ?? "").localeCompare(b.inicio_en ?? ""));

const VIGENTES = ["pendiente_pago", "pendiente_aprobacion", "confirmada"];

export function ViajeReserva({
  reserva,
  cambiar,
  error,
}: {
  reserva: Reserva;
  cambiar: (r: Reserva) => void;
  error: (mensaje: string | null) => void;
}) {
  const lista = viajes(reserva);
  const ida = lista[0];
  const vuelta = lista[1];
  const [editando, setEditando] = useState(false);
  const [pendiente, empezar] = useTransition();
  const ahora = new Date().toISOString();
  const editable =
    VIGENTES.includes(reserva.estado) && lista.some((i) => (i.inicio_en ?? "") > ahora);

  return (
    <section className={estilos.bloque}>
      <h2>{vuelta ? "Ida y vuelta" : "El viaje"}</h2>
      <dl className={estilos.datos}>
        {lista.map((i) => {
          const d = desglose(i);
          const datos = i.datos_servicio;
          return (
            <div key={i.inicio_en ?? d.sentido}>
              <dt>{d.sentido === "vuelta" ? "Vuelta" : vuelta ? "Ida" : "Cuándo"}</dt>
              <dd>
                {i.inicio_en && `${diaAR(i.inicio_en)}, ${horaAR(i.inicio_en)} h`}
                {i.fin_en && ` · llega ${horaAR(i.fin_en)} h aprox.`}
                <br />
                {d.origen} → {d.destino}
                {d.km ? ` · ${String(d.km).replace(".", ",")} km` : ""}
                {datos?.direccion_origen && (
                  <>
                    <br />
                    Te buscan en: {datos.direccion_origen}
                  </>
                )}
                {datos?.direccion_destino && (
                  <>
                    <br />
                    Te dejan en: {datos.direccion_destino}
                  </>
                )}
                {datos?.vuelo && (
                  <>
                    <br />
                    Vuelo o micro: {datos.vuelo}
                  </>
                )}
              </dd>
            </div>
          );
        })}
        <div>
          <dt>Quiénes viajan</dt>
          <dd>
            {plural(ida.adultos, "pasajero", "pasajeros")}
            {desglose(ida).valijas ? ` · ${plural(desglose(ida).valijas!, "valija", "valijas")}` : ""}
          </dd>
        </div>
        {ida.datos_servicio?.notas && (
          <div>
            <dt>Para el chofer</dt>
            <dd>{ida.datos_servicio.notas}</dd>
          </div>
        )}
      </dl>

      {editable && !editando && (
        <button type="button" className={estilos.secundario} onClick={() => setEditando(true)}>
          Cambiar vuelo o notas
        </button>
      )}
      {editable && editando && (
        <form
          className={estilos.motivo}
          action={(f) => {
            const v = (k: string) => String(f.get(k) ?? "").trim();
            empezar(async () => {
              const r = await accionCambiarViaje(reserva.codigo, {
                vuelo_ida: v("vuelo_ida"),
                ...(vuelta ? { vuelo_vuelta: v("vuelo_vuelta") } : {}),
                notas: v("notas"),
              });
              if ("error" in r) error(r.error);
              else {
                error(null);
                cambiar(r.reserva);
                setEditando(false);
              }
            });
          }}
        >
          <span>Vuelo o micro{vuelta ? " de la ida" : ""}</span>
          <input name="vuelo_ida" defaultValue={ida.datos_servicio?.vuelo ?? ""} maxLength={20} />
          {vuelta && (
            <>
              <span>Vuelo o micro de la vuelta</span>
              <input
                name="vuelo_vuelta"
                defaultValue={vuelta.datos_servicio?.vuelo ?? ""}
                maxLength={20}
              />
            </>
          )}
          <span>Para el chofer</span>
          <textarea
            name="notas"
            rows={2}
            maxLength={500}
            defaultValue={ida.datos_servicio?.notas ?? ""}
          />
          <div className={estilos.botones}>
            <button type="submit" className={estilos.principal} disabled={pendiente}>
              Guardar
            </button>
            <button
              type="button"
              className={estilos.secundario}
              disabled={pendiente}
              onClick={() => setEditando(false)}
            >
              No cambiar
            </button>
          </div>
        </form>
      )}
    </section>
  );
}

/* Lo que se paga, viaje por viaje. */
export function PagoViaje({ reserva }: { reserva: Reserva }) {
  const lista = viajes(reserva);
  return (
    <dl className={estilos.desglose}>
      {lista.map((i) => {
        const d = desglose(i);
        const cargo = i.comision ? Number(i.comision.cargo_viajero) : 0;
        return (
          <Fragment key={i.inicio_en ?? d.sentido}>
            {lista.length > 1 && (
              <div className={estilos.totalFila}>
                <dt>{d.sentido === "vuelta" ? "Vuelta" : "Ida"}</dt>
                <dd className="cifra">{pesosExactos(i.total)}</dd>
              </div>
            )}
            {(d.lineas ?? []).map((l) => (
              <div key={l.concepto}>
                <dt>{l.concepto}</dt>
                <dd className="cifra">{pesosExactos(l.monto)}</dd>
              </div>
            ))}
            {cargo > 0 && (
              <div>
                <dt>Cargo de servicio</dt>
                <dd className="cifra">{pesosExactos(i.comision!.cargo_viajero)}</dd>
              </div>
            )}
          </Fragment>
        );
      })}
      <div className={estilos.totalFila}>
        <dt>Total</dt>
        <dd className="cifra">{pesosExactos(reserva.total)}</dd>
      </div>
    </dl>
  );
}
