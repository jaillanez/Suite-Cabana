import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { catalogoAlta } from "@/lib/api";
import { cuentaActual } from "@/lib/sesion";
import Encabezado from "@/componentes/Encabezado";
import FormularioNueva from "@/componentes/FormularioNueva";
import estilos from "../mis.module.css";

export const metadata: Metadata = {
  title: "Nueva publicación",
  robots: { index: false },
};

export default async function Nueva({
  searchParams,
}: {
  searchParams: Promise<{ tipo?: string }>;
}) {
  const cuenta = await cuentaActual();
  if (!cuenta) redirect("/ingresar?volver=/mis-publicaciones/nueva");
  if (!cuenta.prestador) redirect("/cuenta");

  const { tipo } = await searchParams;
  const [alojamiento, salon, excursion, traslado] = await Promise.all([
    catalogoAlta("alojamiento"),
    catalogoAlta("salon_eventos"),
    catalogoAlta("excursion"),
    catalogoAlta("traslado"),
  ]);

  return (
    <>
      <Encabezado />
      <main className={estilos.pagina}>
        <h1>Nueva publicación</h1>
        <p className={estilos.subtitulo}>
          Empezá con el nombre y dónde queda. El resto lo completás después, y
          se guarda como borrador hasta que la mandes a revisión.
        </p>
        <FormularioNueva
          catalogos={{ alojamiento, salon_eventos: salon, excursion, traslado }}
          tipoInicial={
            tipo === "salon_eventos" || tipo === "excursion" || tipo === "traslado"
              ? tipo
              : "alojamiento"
          }
        />
      </main>
    </>
  );
}
