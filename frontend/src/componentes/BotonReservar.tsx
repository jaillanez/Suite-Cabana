"use client";

import { useActionState } from "react";

import Link from "next/link";

import { accionReservar } from "@/lib/acciones-reservas";
import { Alerta } from "./Iconos";
import estilos from "./BotonReservar.module.css";

/* El botón que crea la reserva. Si no hay sesión, la acción manda a ingresar:
   no tiene sentido pedir los datos dos veces. */
export default function BotonReservar({
  unidadId,
  desde,
  hasta,
  adultos,
  mascotas = 0,
  etiqueta,
  deshabilitado = false,
}: {
  unidadId: string;
  desde: string;
  hasta: string;
  adultos: number;
  mascotas?: number;
  etiqueta: string;
  deshabilitado?: boolean;
}) {
  const [estado, ejecutar, pendiente] = useActionState(accionReservar, {} as { error?: string });

  return (
    <form action={ejecutar} className={estilos.formulario}>
      <input type="hidden" name="unidad_id" value={unidadId} />
      <input type="hidden" name="desde" value={desde} />
      <input type="hidden" name="hasta" value={hasta} />
      <input type="hidden" name="adultos" value={adultos} />
      <input type="hidden" name="mascotas" value={mascotas} />

      {estado?.error && (
        <p className={estilos.error} role="alert">
          <Alerta className={estilos.icono} />
          {estado.error}
        </p>
      )}

      <label className={estilos.terminos}>
        <input type="checkbox" name="acepta_terminos" required />
        <span>
          Acepto los <Link href="/terminos">términos</Link> y la política de cancelación de
          este alojamiento.
        </span>
      </label>

      <button type="submit" className={estilos.boton} disabled={pendiente || deshabilitado}>
        {pendiente ? "Reservando…" : etiqueta}
      </button>
    </form>
  );
}
