"use client";

/* Agenda por horas de un espacio (docs/04, etapa 5): qué está tomado cada día y
   bloqueos a mano. Si un bloqueo choca con una reserva lo rechaza el backend; acá
   solo se muestra el motivo. */

import { useEffect, useState, useTransition } from "react";

import {
  accionAgendaHoraria,
  accionBloquearHoras,
  accionSoltarHoras,
  type ResultadoAgendaHoraria,
} from "@/lib/acciones-publicaciones";
import type { AgendaHoraria } from "@/lib/api";
import { diaAR, horaAR, hoyISO } from "@/lib/formato";
import { Alerta, ChevronDer, ChevronIzq, Cruz } from "./Iconos";
import estilos from "./AgendaSalon.module.css";

const DIAS = 7;
// Argentina no tiene horario de verano: el día empieza siempre a las 00 -03.
const inicioDelDia = (iso: string) =>
  new Date(`${iso}T00:00:00-03:00`).getTime();

function sumarDias(iso: string, n: number): string {
  const d = new Date(`${iso}T12:00:00-03:00`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

export default function AgendaSalon({
  publicacionId,
  unidadId,
  vehiculo = false,
}: {
  publicacionId: string;
  unidadId: string;
  /* Un vehículo de traslados (docs/06): la misma agenda, con sus palabras. */
  vehiculo?: boolean;
}) {
  const [desde, setDesde] = useState(hoyISO());
  const [agenda, setAgenda] = useState<AgendaHoraria | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pendiente, empezar] = useTransition();

  function aplicar(r: ResultadoAgendaHoraria) {
    if ("agenda" in r) {
      setAgenda(r.agenda);
      setError(null);
    } else setError(r.error);
  }

  useEffect(() => {
    let vigente = true;
    accionAgendaHoraria(publicacionId, unidadId, desde).then(
      (r) => vigente && aplicar(r),
    );
    return () => {
      vigente = false;
    };
  }, [publicacionId, unidadId, desde]);

  const dias = Array.from({ length: DIAS }, (_, i) => sumarDias(desde, i));

  return (
    <div className={estilos.agenda}>
      <div className={estilos.navegacion}>
        <button
          type="button"
          onClick={() => setDesde(sumarDias(desde, -DIAS))}
          disabled={desde <= hoyISO()}
          aria-label="Semana anterior"
        >
          <ChevronIzq />
        </button>
        <span>
          {diaAR(`${dias[0]}T12:00:00-03:00`)} al{" "}
          {diaAR(`${dias[DIAS - 1]}T12:00:00-03:00`)}
        </span>
        <button
          type="button"
          onClick={() => setDesde(sumarDias(desde, DIAS))}
          aria-label="Semana siguiente"
        >
          <ChevronDer />
        </button>
      </div>

      {error && (
        <p className={estilos.error} role="alert">
          <Alerta className={estilos.icono} />
          {error}
        </p>
      )}

      {!agenda ? (
        <p className={estilos.cargando}>Trayendo la agenda…</p>
      ) : (
        <ol className={estilos.dias}>
          {dias.map((dia) => {
            const a = inicioDelDia(dia);
            const b = a + 24 * 3600 * 1000;
            const delDia = agenda.tramos.filter(
              (t) =>
                new Date(t.inicio).getTime() < b &&
                new Date(t.fin).getTime() > a,
            );
            return (
              <li key={dia}>
                <span className={estilos.dia}>
                  {diaAR(`${dia}T12:00:00-03:00`)}
                </span>
                {delDia.length === 0 ? (
                  <span className={estilos.libre}>Libre</span>
                ) : (
                  <ul className={estilos.tramos}>
                    {delDia.map((t) => (
                      <li key={t.id} data-origen={t.origen}>
                        {/* Un evento que cruza la medianoche aparece en los dos días:
                            en el segundo, solo su parte y aclarado. */}
                        <span className="cifra">
                          {new Date(t.inicio).getTime() < a
                            ? "00:00"
                            : horaAR(t.inicio)}
                          –
                          {new Date(t.fin).getTime() > b
                            ? "24:00"
                            : horaAR(t.fin)}
                        </span>
                        <span>
                          {new Date(t.inicio).getTime() < a && (
                            <small>sigue del día anterior · </small>
                          )}
                          {t.etiqueta}
                          {t.reserva && ` · ${t.reserva}`}
                          {t.nota && <small> · {t.nota}</small>}
                        </span>
                        {t.editable && (
                          <button
                            type="button"
                            disabled={pendiente}
                            onClick={() =>
                              empezar(async () =>
                                aplicar(
                                  await accionSoltarHoras(
                                    publicacionId,
                                    unidadId,
                                    t.id,
                                  ),
                                ),
                              )
                            }
                            aria-label="Liberar este horario"
                          >
                            <Cruz />
                          </button>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            );
          })}
        </ol>
      )}

      {vehiculo ? (
        <p className={estilos.nota}>
          Cada viaje incluye la vuelta a la base, si la elegiste en las reglas
          {agenda && agenda.preparacion_minutos > 0
            ? `, y los ${agenda.preparacion_minutos} min de preparación`
            : ""}
          .
        </p>
      ) : (
        agenda &&
        agenda.preparacion_minutos > 0 && (
          <p className={estilos.nota}>
            Las reservas incluyen los {agenda.preparacion_minutos} min de
            preparación posteriores.
          </p>
        )
      )}

      <form
        className={estilos.bloquear}
        action={(datos) => {
          const v = (k: string) => String(datos.get(k) ?? "").trim();
          empezar(async () => {
            const r = await accionBloquearHoras(publicacionId, unidadId, {
              dia: v("dia"),
              hora_desde: v("hora_desde"),
              hora_hasta: v("hora_hasta"),
              nota: v("nota") || null,
            });
            if ("agenda" in r)
              setDesde(
                v("dia") < desde || v("dia") >= sumarDias(desde, DIAS)
                  ? v("dia")
                  : desde,
              );
            aplicar(r);
          });
        }}
      >
        <label>
          <span>Día</span>
          <input
            name="dia"
            type="date"
            min={hoyISO()}
            defaultValue={desde}
            required
          />
        </label>
        <label>
          <span>Desde</span>
          <input name="hora_desde" type="time" required />
        </label>
        <label>
          <span>Hasta</span>
          <input name="hora_hasta" type="time" required />
        </label>
        <label className={estilos.notaCampo}>
          <span>Para qué (opcional)</span>
          <input
            name="nota"
            maxLength={200}
            placeholder={vehiculo ? "Service, viaje vendido por teléfono" : "Cumple vendido por WhatsApp"}
          />
        </label>
        <button type="submit" disabled={pendiente}>
          Bloquear
        </button>
      </form>
    </div>
  );
}
