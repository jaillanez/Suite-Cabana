import type { Metadata } from "next";
import Link from "next/link";

import { cuentaActual } from "@/lib/sesion";
import Encabezado from "@/componentes/Encabezado";
import estilos from "./publicar.module.css";

export const metadata: Metadata = {
  title: "Sumá tu alojamiento o tu salón",
  description:
    "Cómo publicar tu alojamiento o tu salón de eventos: fotos, precios, disponibilidad y cobro directo a tu cuenta de Mercado Pago.",
};
export default async function Publicar() {
  const cuenta = await cuentaActual();
  return (
    <>
      <Encabezado />
      <main className={estilos.pagina}>
        <h1>Sumá tu alojamiento o tu salón</h1>
        <p className={estilos.bajada}>
          Publicá tus cabañas, y si tenés salón, quincho o espacio para eventos,
          publicalo también: cada uno con sus precios y su disponibilidad.
        </p>

        <section>
          <h2>Cómo va a funcionar</h2>
          {/* El contenido de cada paso va en un solo elemento: la `li` es una
              grilla de dos columnas, y un texto suelto junto al `strong` cae en la
              columna del número —28px— y se parte una palabra por línea. */}
          <ol className={estilos.pasos}>
            <li>
              <span>
                <strong>Creás tu publicación</strong> con fotos, servicios,
                reglas y todas las unidades o espacios que alquiles, cada uno
                con su capacidad.
              </span>
            </li>
            <li>
              <span>
                <strong>Cargás precios y calendario</strong>. Alojamiento:
                precio por noche, temporadas, estadía mínima, y sincronización
                con Booking y Airbnb. Salones: turnos fijos o precio por hora,
                capacidad, adicionales y seña.
              </span>
            </li>
            <li>
              <span>
                <strong>Revisamos la publicación</strong> antes de que salga a
                la vista.
              </span>
            </li>
            <li>
              <span>
                <strong>Cobrás directo</strong>. El pago entra a tu cuenta de
                Mercado Pago: la plataforma no retiene tu plata. La comisión se
                factura aparte.
              </span>
            </li>
          </ol>
        </section>

        <section>
          <h2>Qué vas a necesitar</h2>
          <ul className={estilos.requisitos}>
            <li>CUIT y condición frente al IVA.</li>
            <li>
              Una cuenta de Mercado Pago a tu nombre para recibir los cobros.
            </li>
            <li>Al menos cinco fotos.</li>
            <li>
              La ubicación en el mapa y, para alojamiento, los horarios de
              ingreso y salida.
            </li>
          </ul>
          <p className={estilos.nota}>
            Sin datos fiscales y cuenta de cobro vinculada no se puede publicar:
            es lo que permite que el dinero vaya directo a vos.
          </p>
        </section>

        {cuenta?.prestador ? (
          <p className={estilos.salida}>
            Ya cargaste tus datos de prestador:{" "}
            <Link href="/mis-publicaciones/nueva">publicá un alojamiento</Link>{" "}
            o{" "}
            <Link href="/mis-publicaciones/nueva?tipo=salon_eventos">
              un salón
            </Link>
            . Queda en borrador hasta que la mandes a revisión.
          </p>
        ) : cuenta ? (
          <p className={estilos.salida}>
            Para empezar, cargá tus datos fiscales desde{" "}
            <Link href="/cuenta">tu cuenta</Link>.
          </p>
        ) : (
          <p className={estilos.salida}>
            Para empezar, <Link href="/registrarse">creá tu cuenta</Link>.
            Mientras tanto podés{" "}
            <Link href="/buscar">ver cómo se muestra la oferta</Link>.
          </p>
        )}
      </main>
    </>
  );
}
