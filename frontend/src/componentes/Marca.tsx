import Link from "next/link";

import estilos from "./Marca.module.css";

/* El nombre público todavía no está decidido (ver PRODUCT.md). "Suite Cabaña" es
   el nombre de trabajo; cambiarlo es cambiar este archivo y nada más. */
export const NOMBRE = "Suite Cabaña";

export default function Marca({ compacta = false }: { compacta?: boolean }) {
  return (
    <Link
      href="/"
      className={`${estilos.marca} ${compacta ? estilos.compacta : ""}`}
      aria-label={`${NOMBRE}, ir al inicio`}
    >
      <svg width="26" height="26" viewBox="0 0 26 26" fill="none" aria-hidden="true">
        <path
          d="M4 12.2 13 4.6l9 7.6"
          stroke="currentColor"
          strokeWidth="1.9"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d="M6.4 11.4v8.2a1.4 1.4 0 0 0 1.4 1.4h10.4a1.4 1.4 0 0 0 1.4-1.4v-8.2"
          stroke="currentColor"
          strokeWidth="1.9"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path d="M13 21v-5.2" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" />
      </svg>
      <span>{NOMBRE}</span>
    </Link>
  );
}
