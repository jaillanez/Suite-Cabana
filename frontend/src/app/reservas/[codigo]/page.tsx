import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";

import { ApiError, pasarelas as traerPasarelas, verReserva } from "@/lib/api";
import { cuentaActual, tokenActual } from "@/lib/sesion";
import DetalleReserva from "@/componentes/DetalleReserva";
import Encabezado from "@/componentes/Encabezado";
import estilos from "../reservas.module.css";

export const metadata: Metadata = { title: "Reserva", robots: { index: false } };

export default async function Reserva({ params }: { params: Promise<{ codigo: string }> }) {
  const { codigo } = await params;
  const cuenta = await cuentaActual();
  if (!cuenta) redirect(`/ingresar?volver=/reservas/${codigo}`);

  const token = (await tokenActual())!;
  let reserva;
  try {
    reserva = await verReserva(token, codigo);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }
  const disponibles = await traerPasarelas().catch(() => []);

  return (
    <>
      <Encabezado />
      <main className={estilos.pagina}>
        <DetalleReserva reserva={reserva} pasarelas={disponibles} />
      </main>
    </>
  );
}
