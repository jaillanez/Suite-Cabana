"use client";

import { useState, useTransition } from "react";

import { accionPedirVerificacion, type Estado } from "@/lib/acciones";
import estilos from "./PedirVerificacion.module.css";

/* Mientras no haya envío de correo (Bloque 6), en local la API devuelve el enlace
   para poder completar el circuito. La pantalla lo muestra tal cual, diciendo
   por qué está ahí. */
export default function PedirVerificacion() {
  const [estado, setEstado] = useState<Estado>({});
  const [pendiente, empezar] = useTransition();

  return (
    <div className={estilos.caja}>
      <button
        type="button"
        className={estilos.boton}
        disabled={pendiente}
        onClick={() => empezar(async () => setEstado(await accionPedirVerificacion()))}
      >
        {pendiente ? "Generando…" : "Reenviar verificación"}
      </button>

      {estado.error && (
        <p className={estilos.error} role="alert">
          {estado.error}
        </p>
      )}
      {estado.aviso && <p className={estilos.aviso}>{estado.aviso}</p>}
      {estado.enlace && (
        <p className={estilos.enlace}>
          <a href={estado.enlace}>Verificar mi correo ahora</a>
        </p>
      )}
    </div>
  );
}
