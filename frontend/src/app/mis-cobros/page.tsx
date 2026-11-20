import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { misCobros } from "@/lib/api";
import { pesos, pesosExactos, rangoFechas } from "@/lib/formato";
import { cuentaActual, tokenActual } from "@/lib/sesion";
import Encabezado from "@/componentes/Encabezado";
import Estado from "@/componentes/EstadoReserva";
import estilos from "../reservas/panel.module.css";

export const metadata: Metadata = { title: "Cobros y comisiones", robots: { index: false } };

export default async function MisCobros() {
  const cuenta = await cuentaActual();
  if (!cuenta) redirect("/ingresar?volver=/mis-cobros");
  if (!cuenta.prestador) redirect("/cuenta");

  const token = (await tokenActual())!;
  const cobros = await misCobros(token).catch(() => null);

  return (
    <>
      <Encabezado />
      <main className={estilos.pagina}>
        <h1>Cobros y comisiones</h1>
        <p className={estilos.bajada}>
          Lo que entró por cada reserva confirmada y cuánta comisión se descontó. Es el número
          contra el que podés controlar tu liquidación.
        </p>

        {!cobros || cobros.reservas === 0 ? (
          <div className={estilos.vacio}>
            <h2>Todavía no hay cobros</h2>
            <p>Cuando una reserva quede confirmada, aparece acá con su detalle.</p>
            <Link href="/mis-publicaciones" className={estilos.accion}>
              Ver mis publicaciones
            </Link>
          </div>
        ) : (
          <>
            <dl className={estilos.resumen}>
              <div>
                <dt>Reservas</dt>
                <dd className="cifra">{cobros.reservas}</dd>
              </div>
              <div>
                <dt>Pagó el viajero</dt>
                <dd className="cifra">{pesos(cobros.paga_el_viajero)}</dd>
              </div>
              <div>
                <dt>Comisión</dt>
                <dd className="cifra">−{pesos(cobros.comision)}</dd>
              </div>
              <div className={estilos.destacado}>
                <dt>Te queda</dt>
                <dd className="cifra">{pesos(cobros.te_queda)}</dd>
              </div>
            </dl>

            <div className={estilos.tablaScroll}>
              <table className={estilos.tabla}>
                <thead>
                  <tr>
                    <th>Reserva</th>
                    <th>Alojamiento</th>
                    <th>Fechas</th>
                    <th className={estilos.derecha}>Pagó el viajero</th>
                    <th className={estilos.derecha}>Tu precio</th>
                    <th className={estilos.derecha}>Comisión</th>
                    <th className={estilos.derecha}>Te queda</th>
                    <th>Estado</th>
                  </tr>
                </thead>
                <tbody>
                  {cobros.lineas.map((l) => (
                    <tr key={l.codigo}>
                      <td>
                        <span className="cifra">{l.codigo}</span>
                      </td>
                      <td>
                        <strong>{l.alojamiento}</strong>
                        <span className={estilos.sub}>{l.unidad}</span>
                      </td>
                      <td>{rangoFechas(l.fecha_inicio, l.fecha_fin)}</td>
                      <td className={`${estilos.derecha} cifra`}>
                        {pesosExactos(l.paga_el_viajero)}
                      </td>
                      <td className={`${estilos.derecha} cifra`}>{pesosExactos(l.tu_precio)}</td>
                      <td className={`${estilos.derecha} ${estilos.resta} cifra`}>
                        −{pesosExactos(l.comision)}
                        {Number(l.iva_comision) > 0 && (
                          <span className={estilos.sub}>
                            IVA {pesosExactos(l.iva_comision)}
                          </span>
                        )}
                      </td>
                      <td className={`${estilos.derecha} ${estilos.neto} cifra`}>
                        {pesosExactos(l.te_queda)}
                      </td>
                      <td>
                        <Estado estado={l.estado} />
                        {!l.pagado && <span className={estilos.sub}>sin acreditar</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className={estilos.nota}>
              La comisión de cada reserva es la que regía cuando se hizo: cambiarla después no
              afecta lo ya reservado.
            </p>
          </>
        )}
      </main>
    </>
  );
}
