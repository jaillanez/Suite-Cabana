import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { reservasDelPrestador } from "@/lib/api";
import { cuentaActual, tokenActual } from "@/lib/sesion";
import Encabezado from "@/componentes/Encabezado";
import ReservasPrestador from "@/componentes/ReservasPrestador";
import estilos from "../reservas/reservas.module.css";

export const metadata: Metadata = { title: "Reservas recibidas", robots: { index: false } };

export default async function ReservasRecibidas() {
  const cuenta = await cuentaActual();
  if (!cuenta) redirect("/ingresar?volver=/mis-reservas");
  if (!cuenta.prestador) redirect("/cuenta");

  const token = (await tokenActual())!;
  const reservas = await reservasDelPrestador(token).catch(() => []);

  return (
    <>
      <Encabezado />
      <main className={estilos.pagina}>
        <h1>Reservas recibidas</h1>
        {reservas.length === 0 ? (
          <div className={estilos.vacio}>
            <h2>Todavía no recibiste reservas</h2>
            <p>
              Cuando alguien reserve alguno de tus alojamientos, la vas a ver acá con lo que te
              queda después de la comisión.
            </p>
            <Link href="/mis-publicaciones" className={estilos.accion}>
              Ver mis publicaciones
            </Link>
          </div>
        ) : (
          <ReservasPrestador inicial={reservas} />
        )}
      </main>
    </>
  );
}
