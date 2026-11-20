import type { Metadata } from "next";
import Link from "next/link";

import Encabezado from "@/componentes/Encabezado";
import { Alerta } from "@/componentes/Iconos";
import estilos from "../legal.module.css";

export const metadata: Metadata = {
  title: "Términos y condiciones",
  description: "Cómo funciona el servicio, qué hace la plataforma y qué hace cada parte.",
};

export const VERSION = "2026-09";

export default function Terminos() {
  return (
    <>
      <Encabezado />
      <main className={estilos.pagina}>
        <p className={estilos.borrador}>
          <Alerta className={estilos.icono} />
          <span>
            <strong>Borrador pendiente de revisión legal.</strong> Este texto describe cómo
            funciona el sistema hoy, en lenguaje llano. Antes de abrir al público tiene que
            revisarlo un abogado: hay obligaciones de defensa del consumidor, de protección de
            datos y de habilitación turística que no están resueltas acá.
          </span>
        </p>

        <h1>Términos y condiciones</h1>
        <p className={estilos.version}>Versión {VERSION}</p>

        <section>
          <h2>Qué es esta plataforma</h2>
          <p>
            Es un lugar donde prestadores turísticos publican alojamientos y viajeros los
            reservan y pagan en línea. La plataforma <strong>no es la dueña</strong> de los
            alojamientos ni presta el servicio de hospedaje: conecta a las dos partes, cobra
            una comisión por cada reserva y sostiene el circuito de pago.
          </p>
        </section>

        <section>
          <h2>Quién responde por qué</h2>
          <ul>
            <li>
              <strong>El prestador</strong> responde por el alojamiento: que exista, que esté
              como lo publicó, que esté habilitado donde corresponda, y por recibir al viajero
              en las condiciones acordadas.
            </li>
            <li>
              <strong>El viajero</strong> responde por los datos que carga, por pagar lo
              acordado y por respetar las reglas de la casa.
            </li>
            <li>
              <strong>La plataforma</strong> responde por el funcionamiento del sistema de
              reservas y pagos, por mostrar la información tal como el prestador la cargó, y
              por aplicar las políticas de cancelación publicadas.
            </li>
          </ul>
          <p className={estilos.pendiente}>
            Pendiente de definición: el rol de la plataforma frente a reclamos entre viajero y
            prestador.
          </p>
        </section>

        <section>
          <h2>Precios y comisión</h2>
          <p>
            El precio que se muestra antes de pagar es el total de la estadía para las fechas y
            la cantidad de personas elegidas, con su desglose a la vista. Ese es el precio que
            se cobra: no hay cargos que aparezcan después.
          </p>
          <p>
            La plataforma cobra una comisión por reserva. Según la configuración vigente, la
            puede absorber el prestador, pagarla el viajero como cargo de servicio, o
            repartirse. Cuando el viajero paga una parte, figura en el desglose con ese nombre.
          </p>
          <p>
            La comisión que se aplica es la que rige al momento de reservar, y queda guardada
            con la reserva: cambios posteriores no afectan reservas ya hechas.
          </p>
        </section>

        <section>
          <h2>Reservas y pago</h2>
          <p>
            Al reservar, las fechas quedan retenidas por un tiempo limitado mientras se
            completa el pago. Si el pago no se completa en ese plazo, la retención vence y las
            fechas se liberan.
          </p>
          <p>
            Algunos alojamientos son de confirmación inmediata y otros requieren que el
            prestador acepte. En el segundo caso, el prestador tiene un plazo para responder;
            si no lo hace, la reserva se cancela y se reintegra lo pagado.
          </p>
          <p>
            El pago se procesa a través de la billetera que el viajero elija. La plataforma no
            guarda los datos de la tarjeta.
          </p>
        </section>

        <section>
          <h2>Cancelaciones</h2>
          <p>
            Cada publicación tiene una política de cancelación, visible antes de reservar. Al
            reservar, esa política queda guardada con la reserva y es la que se aplica, aunque
            el prestador la cambie después.
          </p>
          <p className={estilos.pendiente}>
            Pendiente de definición: los porcentajes y plazos definitivos de cada política, y
            la aplicabilidad del botón de arrepentimiento a servicios turísticos con fecha.
          </p>
        </section>

        <section>
          <h2>Publicaciones</h2>
          <p>
            Ninguna publicación es visible sin que la revise un operador de la plataforma. El
            prestador es responsable de que las fotos, la descripción y la ubicación
            correspondan al alojamiento real. Para publicar hace falta tener cargados los datos
            fiscales y una cuenta de cobro vinculada.
          </p>
        </section>

        <section>
          <h2>Cambios en estos términos</h2>
          <p>
            Si estos términos cambian, se avisa y se pide aceptar la versión nueva. Lo que ya
            aceptaste sigue valiendo para las reservas hechas bajo esa versión.
          </p>
        </section>

        <p className={estilos.pie}>
          Ver también la <Link href="/privacidad">política de privacidad</Link>.
        </p>
      </main>
    </>
  );
}
