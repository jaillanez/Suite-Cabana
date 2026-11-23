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
  const [estado, ejecutar, pendiente] = useActionState(
    accionReservar,
    {} as { error?: string; pedirTelefono?: boolean },
  );

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

      {/* Solo si la cuenta no tiene WhatsApp: el backend responde 428 y se pide acá. */}
      {estado?.pedirTelefono && <CampoWhatsApp />}

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

export function CampoWhatsApp({
  valor,
  cambiar,
}: {
  valor?: string;
  cambiar?: (v: string) => void;
}) {
  return (
    <label className={estilos.telefono}>
      <span>Tu WhatsApp</span>
      <input
        name="telefono"
        type="tel"
        autoComplete="tel"
        inputMode="tel"
        placeholder="264 412 3456"
        required
        autoFocus
        {...(cambiar
          ? { value: valor ?? "", onChange: (e) => cambiar(e.target.value) }
          : {})}
      />
      <small>
        Con la reserva confirmada, el anfitrión y vos se pueden escribir desde la reserva.
        Queda guardado en tu cuenta.
      </small>
    </label>
  );
}
