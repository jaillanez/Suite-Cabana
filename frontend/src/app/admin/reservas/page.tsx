import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { comisionesOperador, reservasOperador } from "@/lib/api";
import { pesos, pesosExactos, rangoFechas } from "@/lib/formato";
import { cuentaActual, tokenActual } from "@/lib/sesion";
import Encabezado from "@/componentes/Encabezado";
import Estado from "@/componentes/EstadoReserva";
import estilos from "../../reservas/panel.module.css";

export const metadata: Metadata = { title: "Reservas y comisiones", robots: { index: false } };

const ESTADOS = [
  ["", "Todos los estados"],
  ["pendiente_pago", "Esperando el pago"],
  ["pendiente_aprobacion", "Esperando al prestador"],
  ["confirmada", "Confirmadas"],
  ["cancelada", "Canceladas"],
  ["completada", "Completadas"],
] as const;

export default async function ReservasOperador({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | undefined>>;
}) {
  const cuenta = await cuentaActual();
  if (!cuenta) redirect("/ingresar?volver=/admin/reservas");
  if (!cuenta.es_operador) redirect("/cuenta");

  const sp = await searchParams;
  const filtros = new URLSearchParams();
  for (const clave of ["estado", "desde", "hasta"]) {
    if (sp[clave]) filtros.set(clave, sp[clave]!);
  }

  const token = (await tokenActual())!;
  const [operacion, comisiones] = await Promise.all([
    reservasOperador(token, filtros).catch(() => null),
    comisionesOperador(token).catch(() => null),
  ]);

  const api = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

  return (
    <>
      <Encabezado />
      <main className={estilos.pagina}>
        <h1>Reservas y comisiones</h1>
        <p className={estilos.bajada}>
          Todo lo que se reservó y lo que la plataforma cobró. Los importes de comisión son los
          que quedaron guardados en cada reserva, no un recálculo.
        </p>

        {comisiones && (
          <dl className={estilos.resumen}>
            <div>
              <dt>Reservas cobradas</dt>
              <dd className="cifra">{comisiones.reservas}</dd>
            </div>
            <div>
              <dt>Base de cálculo</dt>
              <dd className="cifra">{pesos(comisiones.base)}</dd>
            </div>
            <div className={estilos.destacado}>
              <dt>Comisión total</dt>
              <dd className="cifra">{pesos(comisiones.comision_total)}</dd>
            </div>
            <div>
              <dt>La paga el viajero</dt>
              <dd className="cifra">{pesos(comisiones.la_paga_el_viajero)}</dd>
            </div>
            <div>
              <dt>La absorbe el prestador</dt>
              <dd className="cifra">{pesos(comisiones.la_absorbe_el_prestador)}</dd>
            </div>
          </dl>
        )}

        <form className={estilos.filtros} method="get">
          <label>
            <span>Estado</span>
            <select name="estado" defaultValue={sp.estado ?? ""}>
              {ESTADOS.map(([valor, nombre]) => (
                <option key={valor} value={valor}>
                  {nombre}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Llegada desde</span>
            <input type="date" name="desde" defaultValue={sp.desde ?? ""} />
          </label>
          <label>
            <span>Llegada hasta</span>
            <input type="date" name="hasta" defaultValue={sp.hasta ?? ""} />
          </label>
          <button type="submit" className={estilos.exportar}>
            Filtrar
          </button>
          <a
            className={estilos.exportar}
            href={`${api}/admin/reservas.csv${filtros.size ? `?${filtros}` : ""}`}
          >
            Descargar CSV
          </a>
        </form>

        {!operacion || operacion.reservas === 0 ? (
          <div className={estilos.vacio}>
            <h2>No hay reservas con esos filtros</h2>
            <p>Probá sacando el estado o ampliando las fechas.</p>
            <Link href="/admin/reservas" className={estilos.accion}>
              Ver todas
            </Link>
          </div>
        ) : (
          <>
            <div className={estilos.tablaScroll}>
              <table className={estilos.tabla}>
                <thead>
                  <tr>
                    <th>Reserva</th>
                    <th>Viajero</th>
                    <th>Prestador</th>
                    <th>Alojamiento</th>
                    <th>Fechas</th>
                    <th className={estilos.derecha}>Total</th>
                    <th className={estilos.derecha}>Comisión</th>
                    <th className={estilos.derecha}>Al prestador</th>
                    <th>Estado</th>
                  </tr>
                </thead>
                <tbody>
                  {operacion.lineas.map((l) => (
                    <tr key={l.codigo}>
                      <td>
                        <span className="cifra">{l.codigo}</span>
                        <span className={estilos.sub}>{l.creada_en}</span>
                      </td>
                      <td>{l.viajero}</td>
                      <td>{l.prestador}</td>
                      <td>
                        <strong>{l.alojamiento}</strong>
                        <span className={estilos.sub}>{l.localidad}</span>
                      </td>
                      <td>{rangoFechas(l.fecha_inicio, l.fecha_fin)}</td>
                      <td className={`${estilos.derecha} cifra`}>{pesosExactos(l.total)}</td>
                      <td className={`${estilos.derecha} cifra`}>
                        {pesosExactos(l.comision)}
                        {Number(l.iva) > 0 && (
                          <span className={estilos.sub}>IVA {pesosExactos(l.iva)}</span>
                        )}
                      </td>
                      <td className={`${estilos.derecha} ${estilos.neto} cifra`}>
                        {pesosExactos(l.al_prestador)}
                      </td>
                      <td>
                        <Estado estado={l.estado} />
                        <span className={estilos.sub}>
                          {l.pagado ? `pagó por ${l.pasarela}` : "sin acreditar"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className={estilos.nota}>
              Mostrando {operacion.reservas} reservas. La descarga incluye hasta 5.000.
            </p>
          </>
        )}
      </main>
    </>
  );
}
