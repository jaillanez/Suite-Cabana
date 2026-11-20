import Link from "next/link";

import { cuentaActual } from "@/lib/sesion";
import { Alerta, Personas } from "./Iconos";
import estilos from "./MenuCuenta.module.css";

/** Estado de sesión en la barra. Sin sesión, invita a entrar; con sesión, avisa
    si falta verificar el correo, que es lo que bloquea reservar. */
export default async function MenuCuenta({ compacto = false }: { compacto?: boolean }) {
  const cuenta = await cuentaActual();

  if (!cuenta) {
    return (
      <Link href="/ingresar" className={`${estilos.ingresar} ${compacto ? estilos.compacto : ""}`}>
        <Personas className={estilos.icono} />
        <span>Ingresar</span>
      </Link>
    );
  }

  return (
    <Link href="/cuenta" className={`${estilos.cuenta} ${compacto ? estilos.compacto : ""}`}>
      <span className={estilos.inicial} aria-hidden="true">
        {cuenta.nombre.charAt(0).toUpperCase()}
      </span>
      <span className={estilos.nombre}>{cuenta.nombre}</span>
      {!cuenta.email_verificado && (
        <Alerta className={estilos.pendiente} titulo="Falta verificar tu correo" />
      )}
    </Link>
  );
}
