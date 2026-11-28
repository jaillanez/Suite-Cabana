"use client";

import { useState, useTransition } from "react";

import {
  accionAprobarReserva,
  accionRechazarReserva,
} from "@/lib/acciones-reservas";
import type { Reserva } from "@/lib/api";
import {
  diaAR,
  horaAR,
  horarioEvento,
  pesos,
  pesosExactos,
  plural,
  rangoFechas,
} from "@/lib/formato";
import Estado from "./EstadoReserva";
import { Alerta } from "./Iconos";
import BotonWhatsApp from "./BotonWhatsApp";
import { esTraslado } from "./ViajeReserva";
import estilos from "./ReservasPrestador.module.css";

export default function ReservasPrestador({ inicial }: { inicial: Reserva[] }) {
  const [reservas, setReservas] = useState(inicial);
  const [motivos, setMotivos] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [pendiente, empezar] = useTransition();

  const actualizar = (r: Reserva) =>
    setReservas((lista) => lista.map((x) => (x.codigo === r.codigo ? r : x)));

  return (
    <>
      {error && (
        <p className={estilos.error} role="alert">
          <Alerta className={estilos.icono} />
          {error}
        </p>
      )}
      <ul className={estilos.lista}>
        {reservas.map((r) => {
          const item = r.items[0];
          const traslado = esTraslado(r);
          // Paquete: las cabañas del evento. En un traslado, la vuelta va en su línea.
          const sumados = traslado ? [] : r.items.slice(1);
          return (
            <li key={r.codigo} className={estilos.ficha}>
              <div className={estilos.encabezado}>
                <div>
                  <strong>{item?.publicacion}</strong>
                  {traslado && <Viajes reserva={r} />}
                  {!traslado && (
                  <span className={estilos.detalle}>
                    {item?.unidad} ·{" "}
                    {item?.inicio_en && item.fin_en
                      ? horarioEvento(item.inicio_en, item.fin_en)
                      : item &&
                        `${rangoFechas(item.fecha_inicio, item.fecha_fin)} · ${plural(
                          item.noches,
                          "noche",
                          "noches",
                        )}`}
                  </span>
                  )}
                  <span className={estilos.detalle}>
                    {item &&
                      plural(
                        item.adultos + item.menores,
                        traslado
                          ? "pasajero"
                          : item.inicio_en && !item.desglose?.pasajeros
                            ? "invitado"
                            : "persona",
                        traslado
                          ? "pasajeros"
                          : item.inicio_en && !item.desglose?.pasajeros
                            ? "invitados"
                            : "personas",
                      )}{" "}
                    · código <span className="cifra">{r.codigo}</span>
                  </span>
                  {sumados.map((s) => (
                    <span key={s.unidad_id} className={estilos.detalle}>
                      + {s.unidad} de {s.publicacion} ·{" "}
                      {rangoFechas(s.fecha_inicio, s.fecha_fin)} ·{" "}
                      {plural(s.adultos + s.menores, "persona", "personas")}
                    </span>
                  ))}
                </div>
                <Estado estado={r.estado} />
              </div>

              <BotonWhatsApp enlace={r.whatsapp} a="al viajero" />

              <dl className={estilos.plata}>
                <div>
                  <dt>Paga el viajero</dt>
                  <dd className="cifra">{pesos(r.total)}</dd>
                </div>
                {Number(r.comision_prestador) > 0 && (
                  <div>
                    <dt>Comisión de la plataforma</dt>
                    <dd className="cifra">
                      −{pesosExactos(r.comision_prestador)}
                    </dd>
                  </div>
                )}
                <div className={estilos.neto}>
                  <dt>Te queda</dt>
                  <dd className="cifra">{pesos(r.neto_prestador)}</dd>
                </div>
              </dl>

              {r.estado === "pendiente_aprobacion" && (
                <div className={estilos.decision}>
                  <p className={estilos.aviso}>
                    Ya pagó. Tenés un plazo para aceptar; si no respondés, se
                    cancela y se le devuelve el dinero.
                  </p>
                  <div className={estilos.botones}>
                    <button
                      type="button"
                      className={estilos.aceptar}
                      disabled={pendiente}
                      onClick={() =>
                        empezar(async () => {
                          const res = await accionAprobarReserva(r.codigo);
                          if ("error" in res) setError(res.error);
                          else actualizar(res.reserva);
                        })
                      }
                    >
                      Aceptar la reserva
                    </button>
                  </div>
                  <details className={estilos.rechazo}>
                    <summary>No puedo tomarla</summary>
                    <label>
                      <span>Motivo (lo va a leer el viajero)</span>
                      <textarea
                        rows={2}
                        value={motivos[r.codigo] ?? ""}
                        onChange={(e) =>
                          setMotivos((m) => ({
                            ...m,
                            [r.codigo]: e.target.value,
                          }))
                        }
                      />
                    </label>
                    <button
                      type="button"
                      disabled={pendiente}
                      onClick={() =>
                        empezar(async () => {
                          const res = await accionRechazarReserva(
                            r.codigo,
                            motivos[r.codigo] ?? "",
                          );
                          if ("error" in res) setError(res.error);
                          else actualizar(res.reserva);
                        })
                      }
                    >
                      Rechazar y devolver el dinero
                    </button>
                  </details>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </>
  );
}

/* Un traslado (docs/06): cada viaje con su hora y recorrido; los datos que cargó
   el viajero (dirección, vuelo, notas) llegan recién con la reserva pagada. */
function Viajes({ reserva }: { reserva: Reserva }) {
  const lista = [...reserva.items].sort((a, b) =>
    (a.inicio_en ?? "").localeCompare(b.inicio_en ?? ""),
  );
  return (
    <>
      {lista.map((i) => {
        const d = i.desglose as { sentido?: string; origen?: string; destino?: string; valijas?: number };
        const datos = i.datos_servicio;
        return (
          <span key={i.inicio_en ?? d.sentido} className={estilos.detalle}>
            {i.unidad} · {d.sentido === "vuelta" ? "Vuelta" : lista.length > 1 ? "Ida" : "Viaje"}{" "}
            {i.inicio_en && `${diaAR(i.inicio_en)}, ${horaAR(i.inicio_en)} h`} · {d.origen} →{" "}
            {d.destino}
            {d.valijas ? ` · ${plural(d.valijas, "valija", "valijas")}` : ""}
            {datos?.direccion_origen && <> · busca en {datos.direccion_origen}</>}
            {datos?.direccion_destino && <> · deja en {datos.direccion_destino}</>}
            {datos?.vuelo && <> · vuelo {datos.vuelo}</>}
            {datos?.notas && <> · “{datos.notas}”</>}
          </span>
        );
      })}
    </>
  );
}
