"use client";

/* Las próximas salidas de una actividad (docs/05, etapa 3): cuántos van, quiénes,
   y lo que el prestador hace con cada una —anotar ventas por fuera, cambiar el
   cupo, suspender—. Lo que se devuelve al suspender lo calcula el backend con el
   porcentaje que eligió el prestador; acá solo se avisa antes. */

import { useEffect, useState, useTransition } from "react";

import {
  accionAgregarSalidaEspecial,
  accionAnotarEnSalida,
  accionCambiarCupoSalida,
  accionQuitarAnotado,
  accionReanudarSalida,
  accionSalidasPanel,
  accionSuspenderSalida,
  type ResultadoSalida,
} from "@/lib/acciones-publicaciones";
import { eleccionDe, type SalidaPanel } from "@/lib/api";
import { diaAR, horaAR, hoyISO, pesos, plural } from "@/lib/formato";
import { Alerta, ChevronDer, ChevronIzq, Cruz } from "./Iconos";
import estilos from "./PanelSalidas.module.css";

const DIAS = 14;

function sumarDias(iso: string, n: number): string {
  const d = new Date(`${iso}T12:00:00-03:00`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

/* Turno + fecha no cambia cuando la salida se guarda (pasa a tener salida_id): con
   el id, la fila se volvía a montar y se cerraba justo después de anotar o suspender. */
const clave = (s: SalidaPanel) => (s.turno_id ? `${s.turno_id}-${s.fecha}` : s.salida_id!);

const ORIGEN: Record<string, string> = {
  reserva: "Reserva",
  retencion: "Pagando",
  externa: "Anotado por vos",
  manual: "Anotado por vos",
};

function estadoMinimo(s: SalidaPanel): string | null {
  if (s.minimo_personas <= 1 || s.suspendida) return null;
  if (s.sale_confirmada) return `Confirmada: llegó al mínimo de ${s.minimo_personas}`;
  const faltan = s.minimo_personas - s.ocupados;
  return faltan > 0
    ? `Mínimo ${s.minimo_personas}: ${faltan === 1 ? "falta 1" : `faltan ${faltan}`}`
    : `Mínimo ${s.minimo_personas}: alcanzado`;
}

function Salida({
  s,
  publicacionId,
  unidadId,
  reintegroSiNoSale,
  onCambio,
  onNota,
}: {
  s: SalidaPanel;
  publicacionId: string;
  unidadId: string;
  reintegroSiNoSale: number;
  onCambio: (r: ResultadoSalida, anterior: SalidaPanel) => void;
  onNota: (mensaje: string) => void;
}) {
  const [pendiente, empezar] = useTransition();
  const [abierta, setAbierta] = useState(false);
  const eleccion = eleccionDe(s);
  const reservas = s.anotados.filter((a) => a.reserva);

  const correr = (accion: () => Promise<ResultadoSalida>) =>
    empezar(async () => onCambio(await accion(), s));

  return (
    <li className={estilos.salida} data-suspendida={s.suspendida || undefined}>
      <button
        type="button"
        className={estilos.resumen}
        aria-expanded={abierta}
        onClick={() => setAbierta(!abierta)}
      >
        <span className={estilos.cuando}>
          <strong>{diaAR(s.inicio)}</strong>
          <span className="cifra">{horaAR(s.inicio)} h</span>
        </span>
        <span className={estilos.nombre}>{s.nombre}</span>
        <span className={estilos.ocupacion}>
          {s.suspendida ? (
            "Suspendida"
          ) : (
            <>
              <span className="cifra">{s.ocupados}</span> de{" "}
              <span className="cifra">{s.cupo}</span>
            </>
          )}
        </span>
        <span className={estilos.barra} aria-hidden>
          <span style={{ width: `${(s.ocupados / s.cupo) * 100}%` }} />
        </span>
      </button>

      {abierta && (
        <div className={estilos.detalle}>
          {s.suspendida && s.motivo && <p className={estilos.motivo}>{s.motivo}</p>}
          {estadoMinimo(s) && <p className={estilos.minimo}>{estadoMinimo(s)}</p>}

          {s.anotados.length > 0 ? (
            <ul className={estilos.anotados}>
              {s.anotados.map((a) => (
                <li key={a.id}>
                  <span>
                    <strong className="cifra">{a.personas}</strong>{" "}
                    {ORIGEN[a.origen] ?? a.origen}
                    {a.reserva && <span className={estilos.codigo}> · {a.reserva}</span>}
                    {a.viajero && <span> · {a.viajero}</span>}
                    {a.nota && !a.reserva && <span> · {a.nota}</span>}
                  </span>
                  {!a.reserva && (
                    <button
                      type="button"
                      disabled={pendiente}
                      onClick={() =>
                        correr(() => accionQuitarAnotado(publicacionId, unidadId, a.id))
                      }
                      aria-label="Liberar estos lugares"
                    >
                      <Cruz />
                    </button>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <p className={estilos.vacia}>Todavía no hay nadie anotado.</p>
          )}

          {!s.suspendida && (
            <>
              <form
                className={estilos.fila}
                action={(datos) => {
                  const personas = Number(datos.get("personas"));
                  const nota = String(datos.get("nota") ?? "").trim() || null;
                  correr(() =>
                    accionAnotarEnSalida(publicacionId, unidadId, {
                      ...eleccion,
                      personas,
                      nota,
                    }),
                  );
                }}
              >
                <input
                  name="personas"
                  type="number"
                  min={1}
                  max={s.libres || 1}
                  required
                  aria-label="Cuántas personas"
                  placeholder="Personas"
                />
                <input
                  name="nota"
                  maxLength={200}
                  placeholder="Quién (vendido por WhatsApp, teléfono…)"
                  aria-label="Nota"
                />
                <button type="submit" disabled={pendiente || s.libres === 0}>
                  Anotar venta por fuera
                </button>
              </form>

              <form
                className={estilos.fila}
                action={(datos) =>
                  correr(() =>
                    accionCambiarCupoSalida(publicacionId, unidadId, {
                      ...eleccion,
                      cupo: Number(datos.get("cupo")),
                    }),
                  )
                }
              >
                <input
                  name="cupo"
                  type="number"
                  min={Math.max(1, s.ocupados, s.minimo_personas)}
                  max={500}
                  defaultValue={s.cupo}
                  required
                  aria-label="Cupo de esta salida"
                />
                <button type="submit" disabled={pendiente}>
                  Cambiar el cupo de este día
                </button>
              </form>

              <form
                className={estilos.fila}
                action={(datos) => {
                  const motivo = String(datos.get("motivo") ?? "").trim();
                  if (
                    reservas.length > 0 &&
                    !window.confirm(
                      `${plural(reservas.length, "reserva", "reservas")} se van a cancelar y ` +
                        `se devuelve el ${reintegroSiNoSale} % de lo pagado. ¿Suspender?`,
                    )
                  )
                    return;
                  empezar(async () => {
                    const r = await accionSuspenderSalida(publicacionId, unidadId, {
                      ...eleccion,
                      motivo,
                    });
                    onCambio(r, s);
                    if ("suspension" in r && r.suspension?.reservas_canceladas) {
                      onNota(
                        `Se cancelaron ${plural(
                          r.suspension.reservas_canceladas,
                          "reserva",
                          "reservas",
                        )}. A devolver: ${pesos(r.suspension.a_devolver)}.`,
                      );
                    }
                  });
                }}
              >
                <input
                  name="motivo"
                  required
                  minLength={3}
                  maxLength={200}
                  placeholder="Motivo (lo ven quienes reservaron)"
                  aria-label="Motivo de la suspensión"
                />
                <button type="submit" className={estilos.peligro} disabled={pendiente}>
                  Suspender
                </button>
              </form>
            </>
          )}

          {s.suspendida && (
            <button
              type="button"
              className={estilos.reanudar}
              disabled={pendiente}
              onClick={() =>
                correr(() => accionReanudarSalida(publicacionId, unidadId, eleccion))
              }
            >
              Volver a ofrecerla
            </button>
          )}
        </div>
      )}
    </li>
  );
}

export default function PanelSalidas({
  publicacionId,
  unidadId,
  reintegroSiNoSale,
}: {
  publicacionId: string;
  unidadId: string;
  reintegroSiNoSale: number;
}) {
  const [desde, setDesde] = useState(hoyISO());
  const [lista, setLista] = useState<SalidaPanel[] | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [nota, setNota] = useState<string | null>(null);
  const [pendiente, empezar] = useTransition();
  const [recarga, setRecarga] = useState(0);
  const hasta = sumarDias(desde, DIAS - 1);

  useEffect(() => {
    let vigente = true;
    accionSalidasPanel(publicacionId, unidadId, desde, hasta).then((r) => {
      if (!vigente) return;
      if ("salidas" in r) setLista(r.salidas);
      else setAviso(r.error);
    });
    return () => {
      vigente = false;
    };
  }, [publicacionId, unidadId, desde, hasta, recarga]);

  function alCambiar(r: ResultadoSalida, anterior: SalidaPanel) {
    if ("error" in r) {
      setAviso(r.error);
      return;
    }
    setAviso(null);
    setNota(null);
    // La salida pudo pasar de "solo del turno" a guardada: se reemplaza por clave vieja.
    setLista((l) => l?.map((x) => (clave(x) === clave(anterior) ? r.salida : x)) ?? l);
  }

  return (
    <div className={estilos.panel}>
      <div className={estilos.navegacion}>
        <button
          type="button"
          onClick={() => setDesde(sumarDias(desde, -DIAS))}
          disabled={desde <= hoyISO()}
          aria-label="Dos semanas antes"
        >
          <ChevronIzq />
        </button>
        <span>
          {diaAR(`${desde}T12:00:00-03:00`)} al {diaAR(`${hasta}T12:00:00-03:00`)}
        </span>
        <button
          type="button"
          onClick={() => setDesde(sumarDias(desde, DIAS))}
          aria-label="Dos semanas después"
        >
          <ChevronDer />
        </button>
      </div>

      {aviso && (
        <p className={estilos.aviso} role="alert">
          <Alerta className={estilos.icono} />
          {aviso}
        </p>
      )}

      {nota && (
        <p className={estilos.nota} role="status">
          {nota}
        </p>
      )}

      {!lista ? (
        <p className={estilos.vacia}>Trayendo las salidas…</p>
      ) : lista.length === 0 ? (
        <p className={estilos.vacia}>No hay salidas en estas dos semanas.</p>
      ) : (
        <ol className={estilos.lista}>
          {lista.map((s) => (
            <Salida
              key={clave(s)}
              s={s}
              publicacionId={publicacionId}
              unidadId={unidadId}
              reintegroSiNoSale={reintegroSiNoSale}
              onCambio={alCambiar}
              onNota={setNota}
            />
          ))}
        </ol>
      )}

      <details className={estilos.especial}>
        <summary>Agregar una salida especial</summary>
        <form
          className={estilos.fila}
          action={(datos) => {
            const v = (k: string) => String(datos.get(k) ?? "").trim();
            empezar(async () => {
              const r = await accionAgregarSalidaEspecial(publicacionId, unidadId, {
                fecha: v("fecha"),
                hora_inicio: v("hora"),
                duracion_minutos: Math.round(Number(v("horas") || 0) * 60),
                cupo: Number(v("cupo")),
                nombre: v("nombre") || null,
                minimo_personas: Number(v("minimo") || 1),
              });
              if ("error" in r) setAviso(r.error);
              else {
                setAviso(null);
                setRecarga((n) => n + 1);
              }
            });
          }}
        >
          <input name="fecha" type="date" min={hoyISO()} max={hoyISO(365)} required aria-label="Día" />
          <input name="hora" type="time" required aria-label="Hora de salida" />
          <input
            name="horas"
            type="number"
            min={0.25}
            max={336}
            step={0.25}
            placeholder="Horas"
            aria-label="Duración en horas"
            required
          />
          <input name="cupo" type="number" min={1} max={500} placeholder="Cupo" required aria-label="Cupo" />
          <input
            name="minimo"
            type="number"
            min={1}
            max={500}
            placeholder="Mínimo"
            aria-label="Mínimo de personas (1: sin mínimo)"
          />
          <input name="nombre" maxLength={200} placeholder="Nota (feriado, grupo…)" aria-label="Nota" />
          <button type="submit" disabled={pendiente}>
            Agregar
          </button>
        </form>
      </details>
    </div>
  );
}
