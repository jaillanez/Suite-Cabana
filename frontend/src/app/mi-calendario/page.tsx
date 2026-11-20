import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { calendarioIntegrado, canales, porRevisar } from "@/lib/api";
import { cuentaActual, tokenActual } from "@/lib/sesion";
import CalendarioGeneral from "@/componentes/CalendarioGeneral";
import Encabezado from "@/componentes/Encabezado";
import VentasDeAfuera from "@/componentes/VentasDeAfuera";
import estilos from "./calendario.module.css";

export const metadata: Metadata = {
  title: "Calendario general",
  robots: { index: false },
};

const VENTANAS = [30, 60, 90, 180] as const;

type Props = { searchParams: Promise<{ dias?: string }> };

export default async function MiCalendario({ searchParams }: Props) {
  const cuenta = await cuentaActual();
  if (!cuenta) redirect("/ingresar?volver=/mi-calendario");
  if (!cuenta.prestador) redirect("/cuenta");

  const { dias: pedido } = await searchParams;
  const dias = VENTANAS.includes(Number(pedido) as (typeof VENTANAS)[number])
    ? Number(pedido)
    : 60;

  const token = await tokenActual();
  const [agenda, plataformas, pendientes] = await Promise.all([
    calendarioIntegrado(token!, new URLSearchParams({ dias: String(dias) })),
    canales(),
    porRevisar(token!).catch(() => []),
  ]);

  return (
    <>
      <Encabezado />
      <main className={estilos.pagina}>
        <div className={estilos.titulo}>
          <div>
            <h1>Calendario general</h1>
            <p>
              Todas tus unidades en una sola grilla, con lo que se vendió acá y lo que se
              vendió en las otras plataformas.
            </p>
          </div>
          <nav className={estilos.ventana} aria-label="Cuántos días mostrar">
            {VENTANAS.map((n) => (
              <a
                key={n}
                href={`/mi-calendario?dias=${n}`}
                aria-current={n === dias ? "page" : undefined}
              >
                {n} días
              </a>
            ))}
          </nav>
        </div>

        <CalendarioGeneral agenda={agenda} plataformas={plataformas} />

        <VentasDeAfuera
          unidades={agenda.unidades}
          plataformas={plataformas}
          pendientes={pendientes}
          direccionBuzon={agenda.direccion_buzon}
        />
      </main>
    </>
  );
}
