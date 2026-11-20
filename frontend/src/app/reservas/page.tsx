import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { misReservas } from "@/lib/api";
import { pesos, plural, rangoFechas } from "@/lib/formato";
import { cuentaActual, tokenActual } from "@/lib/sesion";
import Encabezado from "@/componentes/Encabezado";
import Estado from "@/componentes/EstadoReserva";
import estilos from "./reservas.module.css";

export const metadata: Metadata = { title: "Mis reservas", robots: { index: false } };

export default async function MisReservas() {
  const cuenta = await cuentaActual();
  if (!cuenta) redirect("/ingresar?volver=/reservas");
  const token = (await tokenActual())!;
  const reservas = await misReservas(token).catch(() => []);

  return (
    <>
      <Encabezado />
      <main className={estilos.pagina}>
        <h1>Mis reservas</h1>

        {reservas.length === 0 ? (
          <div className={estilos.vacio}>
            <h2>Todavía no reservaste nada</h2>
            <p>Cuando reserves, vas a poder seguir acá el estado, el pago y la cancelación.</p>
            <Link href="/buscar" className={estilos.accion}>
              Buscar alojamiento
            </Link>
          </div>
        ) : (
          <ul className={estilos.lista}>
            {reservas.map((r) => {
              const item = r.items[0];
              return (
                <li key={r.codigo}>
                  <Link href={`/reservas/${r.codigo}`} className={estilos.fila}>
                    <span className={estilos.miniatura}>
                      {item?.fotos[0] ? (
                        <img src={item.fotos[0].url} alt="" loading="lazy" />
                      ) : (
                        <span className={estilos.sinFoto} />
                      )}
                    </span>
                    <span className={estilos.datos}>
                      <strong>{item?.publicacion}</strong>
                      <span className={estilos.detalle}>
                        {item?.unidad} · {item?.localidad}, {item?.provincia}
                      </span>
                      <span className={estilos.detalle}>
                        {item && rangoFechas(item.fecha_inicio, item.fecha_fin)} ·{" "}
                        {item && plural(item.noches, "noche", "noches")}
                      </span>
                      <span className={`${estilos.codigo} cifra`}>{r.codigo}</span>
                    </span>
                    <span className={estilos.derecha}>
                      <Estado estado={r.estado} />
                      <span className={`${estilos.total} cifra`}>{pesos(r.total)}</span>
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </main>
    </>
  );
}
