import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { misPublicaciones } from "@/lib/api";
import { cuentaActual, tokenActual } from "@/lib/sesion";
import Encabezado from "@/componentes/Encabezado";
import Estado from "@/componentes/EstadoPublicacion";
import { Alerta } from "@/componentes/Iconos";
import estilos from "./mis.module.css";

export const metadata: Metadata = {
  title: "Mis publicaciones",
  robots: { index: false },
};

export default async function MisPublicaciones() {
  const cuenta = await cuentaActual();
  if (!cuenta) redirect("/ingresar?volver=/mis-publicaciones");
  if (!cuenta.prestador) redirect("/cuenta");

  const token = await tokenActual();
  const publicaciones = token
    ? await misPublicaciones(token).catch(() => [])
    : [];

  return (
    <>
      <Encabezado />
      <main className={estilos.pagina}>
        <div className={estilos.titulo}>
          <h1>Mis publicaciones</h1>
          <span className={estilos.accionesTitulo}>
            <Link href="/mi-calendario" className={estilos.secundaria}>
              Calendario general
            </Link>
            <Link href="/mis-publicaciones/nueva" className={estilos.nueva}>
              Nueva publicación
            </Link>
          </span>
        </div>

        {!cuenta.prestador.puede_publicar && (
          <p className={estilos.aviso}>
            <Alerta className={estilos.icono} />
            <span>
              Podés preparar tu publicación, pero para mandarla a revisión falta
              vincular tu cuenta de Mercado Pago. Es lo que hace que el pago
              entre directo a vos.
            </span>
          </p>
        )}

        {publicaciones.length === 0 ? (
          <div className={estilos.vacio}>
            <h2>Todavía no tenés publicaciones</h2>
            <p>
              Creá la primera. Podés guardarla como borrador e ir completándola
              de a poco: se manda a revisión recién cuando esté lista.
            </p>
            <Link href="/mis-publicaciones/nueva" className={estilos.nueva}>
              Crear la primera
            </Link>
          </div>
        ) : (
          <ul className={estilos.lista}>
            {publicaciones.map((p) => (
              <li key={p.id}>
                <Link
                  href={`/mis-publicaciones/${p.id}`}
                  className={estilos.fila}
                >
                  <span className={estilos.miniatura}>
                    {p.fotos[0] ? (
                      <img src={p.fotos[0].url} alt="" loading="lazy" />
                    ) : (
                      <span className={estilos.sinFoto} />
                    )}
                  </span>
                  <span className={estilos.datos}>
                    <strong>{p.titulo}</strong>
                    <span className={estilos.lugar}>
                      {p.tipo === "salon_eventos"
                        ? "Salón de eventos · "
                        : p.tipo === "excursion"
                          ? "Excursión · "
                          : ""}
                      {p.localidad} · {p.provincia}
                    </span>
                    <span className={estilos.numeros}>
                      <span className="cifra">{p.fotos.length}</span> fotos ·{" "}
                      <span className="cifra">{p.unidades.length}</span>{" "}
                      {p.tipo === "salon_eventos"
                        ? p.unidades.length === 1
                          ? "espacio"
                          : "espacios"
                        : p.tipo === "excursion"
                          ? p.unidades.length === 1
                            ? "actividad"
                            : "actividades"
                          : p.unidades.length === 1
                          ? "unidad"
                          : "unidades"}
                      {p.faltantes.length > 0 && (
                        <span className={estilos.faltan}>
                          · {p.faltantes.length === 1 ? "falta" : "faltan"}{" "}
                          <span className="cifra">{p.faltantes.length}</span>{" "}
                          {p.faltantes.length === 1 ? "cosa" : "cosas"}
                        </span>
                      )}
                    </span>
                  </span>
                  <Estado estado={p.estado} />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </main>
    </>
  );
}
