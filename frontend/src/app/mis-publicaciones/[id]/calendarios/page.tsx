import type { Metadata } from "next";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { ApiError, canales, verCalendarios } from "@/lib/api";
import { cuentaActual, tokenActual } from "@/lib/sesion";
import ConectarCalendarios from "@/componentes/ConectarCalendarios";
import Encabezado from "@/componentes/Encabezado";
import estilos from "../../mis.module.css";

export const metadata: Metadata = { title: "Conectar calendarios", robots: { index: false } };

export default async function Calendarios({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const volver = `/mis-publicaciones/${id}/calendarios`;
  const cuenta = await cuentaActual();
  if (!cuenta) redirect(`/ingresar?volver=${volver}`);
  if (!cuenta.prestador) redirect("/cuenta");
  const token = await tokenActual();
  if (!token) redirect(`/ingresar?volver=${volver}`);

  let datos;
  try {
    datos = await verCalendarios(token, id);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    if (e instanceof ApiError && e.status === 409) redirect(`/mis-publicaciones/${id}`);
    throw e;
  }
  const plataformas = await canales().catch(() => []);

  return (
    <>
      <Encabezado />
      <main className={estilos.pagina}>
        <Link href={`/mis-publicaciones/${id}`}>← {datos.titulo}</Link>
        <h1>Conectá tus calendarios</h1>
        <p className={estilos.subtitulo}>
          Si también publicás en Airbnb o Booking, conectalos para que una noche vendida en un
          lugar se bloquee en los otros. Te guiamos paso a paso y te avisamos si algo deja de
          funcionar.
        </p>
        <ConectarCalendarios inicial={datos} plataformas={plataformas} />
      </main>
    </>
  );
}
