"use client";

import { useState, useTransition } from "react";
import Link from "next/link";

import { accionCancelar, accionPagar, accionSimularPago } from "@/lib/acciones-reservas";
import type { PasarelaDisponible, Reserva } from "@/lib/api";
import { pesos, pesosExactos, plural, rangoFechas } from "@/lib/formato";
import Estado, { TEXTOS_RESERVA } from "./EstadoReserva";
import { Alerta, Rayo } from "./Iconos";
import estilos from "./DetalleReserva.module.css";

export default function DetalleReserva({
  reserva: inicial,
  pasarelas,
}: {
  reserva: Reserva;
  pasarelas: PasarelaDisponible[];
}) {
  const [reserva, setReserva] = useState(inicial);
  const [error, setError] = useState<string | null>(null);
  const [motivo, setMotivo] = useState("");
  const [pagoSimulado, setPagoSimulado] = useState<string | null>(null);
  const [pendiente, empezar] = useTransition();

  const item = reserva.items[0];
  const comision = item?.comision;
  const desglose = item?.desglose as Record<string, string> | undefined;
  const hayCargo = comision ? Number(comision.cargo_viajero) > 0 : false;
  const disponibles = pasarelas.filter((p) => p.disponible);
  const puedeCancelar = ["pendiente_pago", "pendiente_aprobacion", "confirmada"].includes(
    reserva.estado,
  );

  function pagar(pasarela: string) {
    empezar(async () => {
      setError(null);
      const r = await accionPagar(reserva.codigo, pasarela);
      if ("error" in r) {
        setError(r.error);
        return;
      }
      if (r.pasarela === "simulada") {
        // En desarrollo no hay a dónde ir: se resuelve acá mismo.
        const url = new URL(r.url);
        setPagoSimulado(url.searchParams.get("pago") ?? null);
      } else {
        window.location.href = r.url;
      }
    });
  }

  function resolverSimulado(estado: string) {
    if (!pagoSimulado) return;
    empezar(async () => {
      const r = await accionSimularPago(pagoSimulado, reserva.codigo, estado);
      if ("error" in r) setError(r.error);
      else window.location.reload();
    });
  }

  return (
    <div className={estilos.detalle}>
      <header className={estilos.cabecera}>
        <div>
          <Link href="/reservas" className={estilos.volver}>
            ← Mis reservas
          </Link>
          <h1>{item?.publicacion}</h1>
          <p className={estilos.lugar}>
            {item?.unidad} · {item?.localidad}, {item?.provincia}
          </p>
        </div>
        <div className={estilos.codigoCaja}>
          <span>Código</span>
          <strong className="cifra">{reserva.codigo}</strong>
        </div>
      </header>

      <div className={estilos.estado}>
        <Estado estado={reserva.estado} />
        <p>{TEXTOS_RESERVA[reserva.estado].explica}</p>
      </div>

      {reserva.motivo_cancelacion && (
        <p className={estilos.cancelada}>
          <Alerta className={estilos.icono} />
          <span>{reserva.motivo_cancelacion}</span>
        </p>
      )}

      {error && (
        <p className={estilos.error} role="alert">
          <Alerta className={estilos.icono} />
          {error}
        </p>
      )}

      <section className={estilos.bloque}>
        <h2>La estadía</h2>
        <dl className={estilos.datos}>
          <div>
            <dt>Fechas</dt>
            <dd>
              {item && rangoFechas(item.fecha_inicio, item.fecha_fin)} ·{" "}
              {item && plural(item.noches, "noche", "noches")}
            </dd>
          </div>
          <div>
            <dt>Personas</dt>
            <dd>
              {item && plural(item.adultos, "adulto", "adultos")}
              {item && item.menores > 0 && `, ${plural(item.menores, "menor", "menores")}`}
              {item && item.mascotas > 0 && `, ${plural(item.mascotas, "mascota", "mascotas")}`}
            </dd>
          </div>
          {item && (item.direccion || item.lat !== null) && (
            <div>
              <dt>Dirección</dt>
              <dd>
                {item.direccion ?? "El anfitrión todavía no la cargó"}
                {item.lat !== null && item.lon !== null && (
                  <>
                    {" · "}
                    <a
                      href={`https://www.openstreetmap.org/?mlat=${item.lat}&mlon=${item.lon}#map=17/${item.lat}/${item.lon}`}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      Ver en el mapa
                    </a>
                  </>
                )}
              </dd>
            </div>
          )}
        </dl>
      </section>

      <section className={estilos.bloque}>
        <h2>Lo que pagás</h2>
        <p className={`${estilos.total} cifra`}>{pesos(reserva.total)}</p>
        {desglose && (
          <dl className={estilos.desglose}>
            <div>
              <dt>Alojamiento</dt>
              <dd className="cifra">{pesosExactos(desglose.alojamiento)}</dd>
            </div>
            {Number(desglose.descuento) > 0 && (
              <div className={estilos.resta}>
                <dt>Descuento por estadía</dt>
                <dd className="cifra">−{pesosExactos(desglose.descuento)}</dd>
              </div>
            )}
            {Number(desglose.limpieza) > 0 && (
              <div>
                <dt>Limpieza</dt>
                <dd className="cifra">{pesosExactos(desglose.limpieza)}</dd>
              </div>
            )}
            {Number(desglose.personas_extra) > 0 && (
              <div>
                <dt>Personas adicionales</dt>
                <dd className="cifra">{pesosExactos(desglose.personas_extra)}</dd>
              </div>
            )}
            {Number(desglose.mascotas) > 0 && (
              <div>
                <dt>Mascotas</dt>
                <dd className="cifra">{pesosExactos(desglose.mascotas)}</dd>
              </div>
            )}
            {hayCargo && comision && (
              <div>
                <dt>Cargo de servicio</dt>
                <dd className="cifra">{pesosExactos(comision.cargo_viajero)}</dd>
              </div>
            )}
            <div className={estilos.totalFila}>
              <dt>Total</dt>
              <dd className="cifra">{pesosExactos(reserva.total)}</dd>
            </div>
          </dl>
        )}
        {reserva.monto_sena && (
          <p className={estilos.nota}>
            El prestador acepta seña: <span className="cifra">{pesos(reserva.monto_sena)}</span>.
          </p>
        )}
      </section>

      {reserva.estado === "pendiente_pago" && (
        <section className={estilos.bloque}>
          <h2>Pagar</h2>
          {disponibles.length === 0 ? (
            <p className={estilos.sinPasarelas}>
              No hay ninguna forma de pago habilitada todavía. El equipo tiene que cargar las
              credenciales de al menos una billetera.
            </p>
          ) : pagoSimulado ? (
            <div className={estilos.simulado}>
              <p>
                <strong>Pago simulado.</strong> No hay dinero real: elegí qué habría contestado
                la billetera.
              </p>
              <div className={estilos.botones}>
                <button
                  type="button"
                  className={estilos.principal}
                  disabled={pendiente}
                  onClick={() => resolverSimulado("aprobado")}
                >
                  Aprobar el pago
                </button>
                <button
                  type="button"
                  className={estilos.secundario}
                  disabled={pendiente}
                  onClick={() => resolverSimulado("rechazado")}
                >
                  Rechazarlo
                </button>
              </div>
            </div>
          ) : (
            <>
              <ul className={estilos.pasarelas}>
                {disponibles.map((p) => (
                  <li key={p.codigo}>
                    <button type="button" disabled={pendiente} onClick={() => pagar(p.codigo)}>
                      <strong>{p.nombre}</strong>
                      {p.reparte_automaticamente && (
                        <span className={estilos.reparte}>
                          <Rayo />
                          El prestador cobra directo
                        </span>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
              {pasarelas.some((p) => !p.disponible) && (
                <details className={estilos.otras}>
                  <summary>Otras billeteras</summary>
                  <ul>
                    {pasarelas
                      .filter((p) => !p.disponible)
                      .map((p) => (
                        <li key={p.codigo}>
                          <strong>{p.nombre}</strong>
                          <span>{p.motivo}</span>
                        </li>
                      ))}
                  </ul>
                </details>
              )}
            </>
          )}
        </section>
      )}

      {reserva.politica_cancelacion && (
        <section className={estilos.bloque}>
          <h2>Cancelación {reserva.politica_cancelacion.nombre.toLowerCase()}</h2>
          <ul className={estilos.tramos}>
            {reserva.politica_cancelacion.tramos.map((t) => (
              <li key={t.dias_antes}>
                <span>
                  {t.dias_antes === 0
                    ? "El mismo día"
                    : `Hasta ${plural(t.dias_antes, "día", "días")} antes`}
                </span>
                <span className="cifra">{t.porcentaje_reintegro}%</span>
              </li>
            ))}
          </ul>
          {reserva.reintegro_si_cancela && (
            <p className={estilos.nota}>
              Si cancelás ahora: <strong>{reserva.reintegro_si_cancela.porcentaje}%</strong> (
              <span className="cifra">{pesos(reserva.reintegro_si_cancela.monto)}</span>).{" "}
              {reserva.reintegro_si_cancela.motivo}.
            </p>
          )}
        </section>
      )}

      {puedeCancelar && (
        <section className={estilos.bloque}>
          <h2>Cancelar</h2>
          <label className={estilos.motivo}>
            <span>Contanos por qué (opcional)</span>
            <textarea
              rows={2}
              value={motivo}
              onChange={(e) => setMotivo(e.target.value)}
              maxLength={300}
            />
          </label>
          <button
            type="button"
            className={estilos.cancelar}
            disabled={pendiente}
            onClick={() =>
              empezar(async () => {
                const r = await accionCancelar(reserva.codigo, motivo);
                if ("error" in r) setError(r.error);
                else setReserva(r.reserva);
              })
            }
          >
            Cancelar la reserva
          </button>
        </section>
      )}
    </div>
  );
}
