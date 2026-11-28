import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import {
  accionAltaPrestador,
  accionDesvincularMercadoPago,
  accionSalir,
  accionVincularMercadoPago,
} from "@/lib/acciones";
import { cuentaActual } from "@/lib/sesion";
import Encabezado from "@/componentes/Encabezado";
import FormularioAuth from "@/componentes/FormularioAuth";
import { Alerta, Rayo } from "@/componentes/Iconos";
import CambiarTelefono from "@/componentes/CambiarTelefono";
import PedirVerificacion from "@/componentes/PedirVerificacion";
import estilos from "./cuenta.module.css";

export const metadata: Metadata = { title: "Mi cuenta", robots: { index: false } };

export default async function Cuenta() {
  const cuenta = await cuentaActual();
  if (!cuenta) redirect("/ingresar?volver=/cuenta");

  const roles = [
    cuenta.es_viajero && "Viajero",
    cuenta.es_prestador && "Prestador",
    cuenta.es_operador && "Operador",
  ].filter(Boolean) as string[];

  return (
    <>
      <Encabezado />
      <main className={estilos.pagina}>
        <div className={estilos.titulo}>
          <h1>
            Hola, {cuenta.nombre} {cuenta.apellido}
          </h1>
          <form action={accionSalir}>
            <button type="submit" className={estilos.salir}>
              Cerrar sesión
            </button>
          </form>
        </div>

        <section>
          <h2>Tus datos</h2>
          <dl className={estilos.datos}>
            <div>
              <dt>Correo</dt>
              <dd>{cuenta.email}</dd>
            </div>
            <div>
              <dt>WhatsApp</dt>
              <dd>
                <CambiarTelefono actual={cuenta.telefono} />
              </dd>
            </div>
            <div>
              <dt>Rol</dt>
              <dd>{roles.join(" y ")}</dd>
            </div>
          </dl>
        </section>

        <section>
          <h2>Tus reservas</h2>
          <p className={estilos.accionesCuenta}>
            <Link href="/reservas" className={estilos.accionChica}>
              Ver mis reservas
            </Link>{" "}
            <Link href="/favoritos" className={estilos.accionChica}>
              Guardados
            </Link>
          </p>
        </section>

        <section>
          <h2>Verificación</h2>
          {cuenta.email_verificado ? (
            <p className={estilos.ok}>
              <Rayo />
              Tu correo está verificado. Podés reservar.
            </p>
          ) : (
            <>
              <p className={estilos.pendiente}>
                <Alerta className={estilos.icono} />
                Tu correo todavía no está verificado. Sin eso no vas a poder reservar.
              </p>
              <PedirVerificacion />
            </>
          )}
        </section>

        <section>
          <h2>Publicar tu alojamiento</h2>
          {cuenta.prestador ? (
            <>
              <dl className={estilos.datos}>
                <div>
                  <dt>Razón social</dt>
                  <dd>{cuenta.prestador.razon_social}</dd>
                </div>
                <div>
                  <dt>CUIT</dt>
                  <dd className="cifra">{cuenta.prestador.cuit}</dd>
                </div>
                <div>
                  <dt>Condición IVA</dt>
                  <dd>{cuenta.prestador.condicion_iva}</dd>
                </div>
              </dl>
              <p className={estilos.accionesCuenta}>
                <Link href="/mis-publicaciones" className={estilos.accionChica}>
                  Ir a mis publicaciones
                </Link>{" "}
                <Link href="/mi-calendario" className={estilos.accionChica}>
                  Calendario general
                </Link>{" "}
                <Link href="/mis-reservas" className={estilos.accionChica}>
                  Reservas recibidas
                </Link>{" "}
                <Link href="/mis-cobros" className={estilos.accionChica}>
                  Cobros y comisiones
                </Link>
              </p>
              {cuenta.prestador.puede_publicar ? (
                <p className={estilos.ok}>
                  <Rayo />
                  Tenés todo listo para publicar.
                </p>
              ) : (
                <p className={estilos.pendiente}>
                  <Alerta className={estilos.icono} />
                  Falta vincular tu cuenta de Mercado Pago. Sin eso no podés publicar, porque
                  es lo que hace que el pago entre directo a vos.
                </p>
              )}
            </>
          ) : (
            <>
              <p className={estilos.bajada}>
                Cargá tus datos fiscales para sumar el rol de prestador. Seguís siendo viajero
                con la misma cuenta.
              </p>
              <FormularioAuth
                accion={accionAltaPrestador}
                enviar="Guardar datos de prestador"
                campos={[
                  {
                    nombre: "razon_social",
                    etiqueta: "Razón social o nombre",
                    ancho: "completo",
                  },
                  {
                    nombre: "cuit",
                    etiqueta: "CUIT",
                    ayuda: "11 dígitos, con o sin guiones.",
                    ancho: "medio",
                  },
                  {
                    nombre: "condicion_iva",
                    etiqueta: "Condición frente al IVA",
                    ayuda: "Monotributo, Responsable inscripto…",
                    ancho: "medio",
                  },
                ]}
              />
            </>
          )}
        </section>

        {cuenta.prestador && (
          <section id="cobros">
            <h2>Cobros con Mercado Pago</h2>
            {cuenta.prestador.cuenta_cobro ? (
              <>
                <p className={estilos.ok}>
                  <Rayo />
                  Cobrás en la cuenta <strong>{cuenta.prestador.cuenta_cobro}</strong>. Lo que
                  te reserven entra directo ahí.
                </p>
                <form action={accionDesvincularMercadoPago}>
                  <button type="submit" className={estilos.salir}>
                    Desvincular cuenta
                  </button>
                </form>
                <p className={estilos.nota}>
                  Si desvinculás, tus alojamientos no se pueden reservar hasta que cargues
                  otra.
                </p>
              </>
            ) : (
              <>
                <p className={estilos.bajada}>
                  Pegá el Access Token de producción de tu cuenta. Lo sacás en Mercado Pago
                  Developers → Tus integraciones → Credenciales de producción. Lo probamos con
                  Mercado Pago antes de guardarlo y queda cifrado: nadie lo vuelve a ver, ni
                  vos.
                </p>
                <FormularioAuth
                  accion={accionVincularMercadoPago}
                  enviar="Vincular Mercado Pago"
                  campos={[
                    {
                      nombre: "access_token",
                      etiqueta: "Access Token",
                      tipo: "password",
                      autoComplete: "off",
                      ayuda: "Empieza con APP_USR-",
                      ancho: "completo",
                    },
                  ]}
                />
              </>
            )}
          </section>
        )}

        {cuenta.es_operador && (
          <section>
            <h2>Operación</h2>
            <p className={estilos.bajada}>
              Ninguna publicación se ve en el sitio sin que vos la apruebes.
            </p>
            <p className={estilos.accionesCuenta}>
              <Link href="/admin/publicaciones" className={estilos.accionChica}>
                Publicaciones esperando aprobación
              </Link>{" "}
              <Link href="/admin/reservas" className={estilos.accionChica}>
                Reservas y comisiones
              </Link>{" "}
              <Link href="/admin/comisiones" className={estilos.accionChica}>
                Reglas de comisión
              </Link>
            </p>
          </section>
        )}

        <p className={estilos.pie}>
          <Link href="/buscar">Buscar alojamiento</Link>
        </p>
      </main>
    </>
  );
}
