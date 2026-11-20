import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { colaOperador, resumenOperador } from "@/lib/api";
import { cuentaActual, tokenActual } from "@/lib/sesion";
import ColaOperador from "@/componentes/ColaOperador";
import Encabezado from "@/componentes/Encabezado";
import estilos from "./admin.module.css";

export const metadata: Metadata = { title: "Aprobaciones", robots: { index: false } };

export default async function Aprobaciones() {
  const cuenta = await cuentaActual();
  if (!cuenta) redirect("/ingresar?volver=/admin/publicaciones");
  if (!cuenta.es_operador) redirect("/cuenta");

  const token = (await tokenActual())!;
  const [cola, resumen] = await Promise.all([
    colaOperador(token).catch(() => []),
    resumenOperador(token).catch(() => null),
  ]);

  return (
    <>
      <Encabezado />
      <main className={estilos.pagina}>
        <h1>Publicaciones esperando aprobación</h1>
        <p className={estilos.bajada}>
          Ninguna publicación se ve en el sitio sin que una persona la mire. Si algo no está,
          devolvela con el motivo: el prestador necesita saber qué corregir.
        </p>

        {resumen && (
          <dl className={estilos.resumen}>
            {[
              ["En revisión", resumen.en_revision],
              ["Publicadas", resumen.aprobadas],
              ["Devueltas", resumen.rechazadas],
              ["Borradores", resumen.borradores],
            ].map(([nombre, valor]) => (
              <div key={nombre as string}>
                <dt>{nombre}</dt>
                <dd className="cifra">{valor}</dd>
              </div>
            ))}
          </dl>
        )}

        <ColaOperador inicial={cola} />
      </main>
    </>
  );
}
