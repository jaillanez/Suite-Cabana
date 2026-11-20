import type { Metadata } from "next";
import Link from "next/link";

import { cuentaActual } from "@/lib/sesion";
import Encabezado from "@/componentes/Encabezado";
import estilos from "./publicar.module.css";

export const metadata: Metadata = {
  title: "Sumá tu alojamiento",
  description:
    "Cómo publicar tu alojamiento. El alta pública todavía no está abierta: arrancamos con un grupo inicial de prestadores.",
};

/* Página honesta: el alta de publicaciones es el Bloque 2 del plan y todavía no
   existe. Antes que un formulario que no hace nada, se explica el estado real. */
export default async function Publicar() {
  const cuenta = await cuentaActual();
  return (
    <>
      <Encabezado />
      <main className={estilos.pagina}>
        <h1>Sumá tu alojamiento</h1>
        <p className={estilos.bajada}>
          Todavía no abrimos el alta pública. Estamos arrancando con un grupo inicial de
          prestadores para probar el circuito completo —publicación, reserva y cobro— antes de
          abrirlo a todos.
        </p>

        <section>
          <h2>Cómo va a funcionar</h2>
          {/* El contenido de cada paso va en un solo elemento: la `li` es una
              grilla de dos columnas, y un texto suelto junto al `strong` cae en la
              columna del número —28px— y se parte una palabra por línea. */}
          <ol className={estilos.pasos}>
            <li>
              <span>
                <strong>Creás tu publicación</strong> con fotos, servicios, reglas de la casa y
                todas las unidades que alquiles, cada una con su capacidad.
              </span>
            </li>
            <li>
              <span>
                <strong>Cargás tarifas y calendario</strong>: precio por noche, temporadas,
                estadía mínima, cargos y descuentos. Podés sincronizar con Booking y Airbnb por
                iCal para que nunca se superpongan las fechas.
              </span>
            </li>
            <li>
              <span>
                <strong>Revisamos la publicación</strong> antes de que salga a la vista.
              </span>
            </li>
            <li>
              <span>
                <strong>Cobrás directo</strong>. El pago entra a tu cuenta de Mercado Pago y la
                comisión se descuenta en la misma operación: la plataforma no retiene tu plata.
              </span>
            </li>
          </ol>
        </section>

        <section>
          <h2>Qué vas a necesitar</h2>
          <ul className={estilos.requisitos}>
            <li>CUIT y condición frente al IVA.</li>
            <li>Una cuenta de Mercado Pago a tu nombre para recibir los cobros.</li>
            <li>Al menos cinco fotos del alojamiento.</li>
            <li>La ubicación en el mapa y los horarios de ingreso y salida.</li>
          </ul>
          <p className={estilos.nota}>
            Sin datos fiscales y cuenta de cobro vinculada no se puede publicar: es lo que
            permite que el dinero vaya directo a vos.
          </p>
        </section>

        {cuenta?.prestador ? (
          <p className={estilos.salida}>
            Ya cargaste tus datos de prestador:{" "}
            <Link href="/mis-publicaciones">armá tu publicación</Link>. Queda en borrador hasta
            que la mandes a revisión.
          </p>
        ) : cuenta ? (
          <p className={estilos.salida}>
            Para empezar, cargá tus datos fiscales desde <Link href="/cuenta">tu cuenta</Link>.
          </p>
        ) : (
          <p className={estilos.salida}>
            Para empezar, <Link href="/registrarse">creá tu cuenta</Link>. Mientras tanto podés{" "}
            <Link href="/buscar">ver cómo se muestra la oferta</Link>.
          </p>
        )}
      </main>
    </>
  );
}
