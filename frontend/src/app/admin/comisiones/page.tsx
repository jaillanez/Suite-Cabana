import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { catalogoComisiones, reglasComision } from "@/lib/api";
import { cuentaActual, tokenActual } from "@/lib/sesion";
import Encabezado from "@/componentes/Encabezado";
import PanelComisiones from "@/componentes/PanelComisiones";
import estilos from "../../reservas/panel.module.css";

export const metadata: Metadata = { title: "Reglas de comisión", robots: { index: false } };

export default async function ReglasDeComision() {
  const cuenta = await cuentaActual();
  if (!cuenta) redirect("/ingresar?volver=/admin/comisiones");
  if (!cuenta.es_operador) redirect("/cuenta");

  const token = (await tokenActual())!;
  const [reglas, catalogo] = await Promise.all([
    reglasComision(token),
    catalogoComisiones(token),
  ]);

  return (
    <>
      <Encabezado />
      <main className={estilos.pagina}>
        <h1>Reglas de comisión</h1>
        <p className={estilos.bajada}>
          Cuánto cobra la plataforma por cada tipo de servicio, zona o temporada. Cuando varias
          reglas coinciden con una reserva gana la más específica (un subtipo le gana a su
          tipo; una localidad, a su provincia); si empatan, la de mayor prioridad. Cambiar una
          regla no toca las reservas ya hechas: cada una guardó la suya.{" "}
          <Link href="/admin/reservas">Ver lo cobrado</Link>.
        </p>
        <PanelComisiones inicial={reglas} catalogo={catalogo} />
      </main>
    </>
  );
}
