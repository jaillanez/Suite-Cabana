import type { Metadata } from "next";
import Link from "next/link";

import Encabezado from "@/componentes/Encabezado";
import { Alerta } from "@/componentes/Iconos";
import estilos from "../legal.module.css";

export const metadata: Metadata = {
  title: "Política de privacidad",
  description: "Qué datos se guardan, para qué, y qué podés pedir sobre ellos.",
};

export default function Privacidad() {
  return (
    <>
      <Encabezado />
      <main className={estilos.pagina}>
        <p className={estilos.borrador}>
          <Alerta className={estilos.icono} />
          <span>
            <strong>Borrador pendiente de revisión legal.</strong> Describe qué hace el sistema
            hoy con los datos. La Ley 25.326 de protección de datos personales impone
            obligaciones que todavía no están verificadas acá.
          </span>
        </p>

        <h1>Política de privacidad</h1>
        <p className={estilos.version}>Versión 2026-09</p>

        <section>
          <h2>Qué datos se guardan</h2>
          <ul>
            <li>
              <strong>De todos:</strong> nombre, apellido, correo y, si lo cargás, teléfono.
            </li>
            <li>
              <strong>Al reservar:</strong> las fechas, la cantidad de personas, el importe y
              el estado de la reserva y del pago.
            </li>
            <li>
              <strong>De los prestadores:</strong> razón social, CUIT, condición frente al IVA
              y el identificador de la cuenta de cobro.
            </li>
          </ul>
          <p>
            Los datos de la tarjeta <strong>no se guardan</strong>: los maneja la billetera que
            procesa el pago.
          </p>
        </section>

        <section>
          <h2>Para qué se usan</h2>
          <p>
            Para operar el servicio: crear la cuenta, mostrar y cobrar reservas, avisarte por
            correo o WhatsApp lo que pasa con ellas, liquidar la comisión y atender reclamos.
            No se venden ni se ceden a terceros con fines publicitarios.
          </p>
        </section>

        <section>
          <h2>Con quién se comparten</h2>
          <ul>
            <li>
              <strong>Con el prestador</strong>, cuando reservás: tu nombre y las fechas. Su
              dirección exacta se te comparte al confirmar.
            </li>
            <li>
              <strong>Con la billetera</strong> que procesa el pago, lo necesario para cobrar.
            </li>
            <li>
              <strong>Con otras plataformas</strong>, si el prestador sincroniza calendarios:
              solo qué noches están ocupadas. Nunca quién reservó ni cuánto pagó.
            </li>
          </ul>
        </section>

        <section>
          <h2>Tus derechos</h2>
          <p>
            Podés pedir acceso a tus datos, que se corrijan, o que se eliminen. Algunos datos
            de reservas y pagos hay que conservarlos por obligaciones fiscales y contables aun
            después de que cierres la cuenta.
          </p>
          <p className={estilos.pendiente}>
            Pendiente: el canal formal para ejercer estos derechos y el plazo de respuesta.
          </p>
        </section>

        <p className={estilos.pie}>
          Ver también los <Link href="/terminos">términos y condiciones</Link>.
        </p>
      </main>
    </>
  );
}
