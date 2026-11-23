/* Abre WhatsApp con el mensaje ya escrito. El enlace lo arma el backend y solo
   existe con la reserva confirmada (app/services/contacto.py): acá no se decide
   nada, solo se muestra. */

import { Mensaje } from "./Iconos";
import estilos from "./BotonWhatsApp.module.css";

export default function BotonWhatsApp({
  enlace,
  a,
}: {
  enlace: string | null;
  /** A quién se le escribe: "al anfitrión", "a Ana". */
  a: string;
}) {
  if (!enlace) return null;
  return (
    <a
      className={estilos.boton}
      href={enlace}
      target="_blank"
      rel="noopener noreferrer"
    >
      <Mensaje className={estilos.icono} />
      Escribirle {a} por WhatsApp
    </a>
  );
}
