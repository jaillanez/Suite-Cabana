"use client";

import { useState, useTransition } from "react";

import { accionFavorito } from "@/lib/acciones-panel";
import { Corazon } from "./Iconos";
import estilos from "./BotonFavorito.module.css";

/* El corazón de la tarjeta. Si no hay sesión lo dice en lugar de fallar callado:
   el viajero acaba de tocar algo y necesita saber qué pasó. */
export default function BotonFavorito({
  publicacionId,
  inicial = false,
}: {
  publicacionId: string;
  inicial?: boolean;
}) {
  const [guardado, setGuardado] = useState(inicial);
  const [aviso, setAviso] = useState<string | null>(null);
  const [pendiente, empezar] = useTransition();

  return (
    <>
      <button
        type="button"
        className={`${estilos.boton} ${guardado ? estilos.activo : ""}`}
        aria-pressed={guardado}
        aria-label={guardado ? "Sacar de favoritos" : "Guardar en favoritos"}
        disabled={pendiente}
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          empezar(async () => {
            const r = await accionFavorito(publicacionId, !guardado);
            if ("error" in r) {
              setAviso(r.error);
              setTimeout(() => setAviso(null), 3000);
            } else {
              setGuardado(r.guardado);
            }
          });
        }}
      >
        <Corazon relleno={guardado} />
      </button>
      {aviso && <span className={estilos.aviso}>{aviso}</span>}
    </>
  );
}
