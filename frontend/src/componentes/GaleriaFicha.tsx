"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ChevronDer, ChevronIzq, Cruz } from "./Iconos";
import estilos from "./GaleriaFicha.module.css";

type Foto = { url: string; descripcion: string | null };

export default function GaleriaFicha({ fotos, titulo }: { fotos: Foto[]; titulo: string }) {
  const [abierta, setAbierta] = useState<number | null>(null);
  const dialogo = useRef<HTMLDialogElement>(null);

  const mover = useCallback(
    (paso: number) =>
      setAbierta((i) => (i === null ? null : (i + paso + fotos.length) % fotos.length)),
    [fotos.length],
  );

  useEffect(() => {
    const d = dialogo.current;
    if (!d) return;
    if (abierta !== null && !d.open) d.showModal();
    if (abierta === null && d.open) d.close();
  }, [abierta]);

  useEffect(() => {
    const teclas = (e: KeyboardEvent) => {
      if (abierta === null) return;
      if (e.key === "ArrowRight") mover(1);
      if (e.key === "ArrowLeft") mover(-1);
    };
    document.addEventListener("keydown", teclas);
    return () => document.removeEventListener("keydown", teclas);
  }, [abierta, mover]);

  if (fotos.length === 0) {
    return (
      <div className={estilos.sinFotos}>
        {/* Sirve para cualquier ficha: alojamiento, salón, excursión o traslado. */}
        <p>Todavía no hay fotos.</p>
      </div>
    );
  }

  const [principal, ...resto] = fotos;
  const mosaico = resto.slice(0, 4);

  return (
    <>
      <div className={`${estilos.mosaico} ${mosaico.length === 0 ? estilos.sola : ""}`}>
        <button type="button" className={estilos.principal} onClick={() => setAbierta(0)}>
          <img src={principal.url} alt={`${titulo}, foto principal`} />
        </button>
        {mosaico.map((f, i) => (
          <button key={f.url} type="button" className={estilos.chica} onClick={() => setAbierta(i + 1)}>
            <img src={f.url} alt={`${titulo}, foto ${i + 2}`} loading="lazy" />
          </button>
        ))}
        {fotos.length > 5 && (
          <button type="button" className={estilos.todas} onClick={() => setAbierta(0)}>
            Ver las {fotos.length} fotos
          </button>
        )}
      </div>

      <dialog ref={dialogo} className={estilos.visor} onClose={() => setAbierta(null)}>
        {abierta !== null && (
          <>
            <img src={fotos[abierta].url} alt={fotos[abierta].descripcion ?? titulo} />
            <p className={estilos.pie}>
              <span className="cifra">
                {abierta + 1} / {fotos.length}
              </span>
              {fotos[abierta].descripcion && <span>{fotos[abierta].descripcion}</span>}
            </p>
            {fotos.length > 1 && (
              <>
                <button
                  type="button"
                  className={`${estilos.flecha} ${estilos.izq}`}
                  onClick={() => mover(-1)}
                  aria-label="Foto anterior"
                >
                  <ChevronIzq />
                </button>
                <button
                  type="button"
                  className={`${estilos.flecha} ${estilos.der}`}
                  onClick={() => mover(1)}
                  aria-label="Foto siguiente"
                >
                  <ChevronDer />
                </button>
              </>
            )}
          </>
        )}
        <button
          type="button"
          className={estilos.cerrar}
          onClick={() => setAbierta(null)}
          aria-label="Cerrar galería"
        >
          <Cruz />
        </button>
      </dialog>
    </>
  );
}
