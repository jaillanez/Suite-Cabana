import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";

import { ApiError, catalogoAlta, miPublicacion } from "@/lib/api";
import { cuentaActual, tokenActual } from "@/lib/sesion";
import EditorPublicacion from "@/componentes/EditorPublicacion";
import Encabezado from "@/componentes/Encabezado";
import estilos from "../mis.module.css";

export const metadata: Metadata = { title: "Editar publicación", robots: { index: false } };

export default async function Editar({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const cuenta = await cuentaActual();
  if (!cuenta) redirect(`/ingresar?volver=/mis-publicaciones/${id}`);
  if (!cuenta.prestador) redirect("/cuenta");

  const token = await tokenActual();
  if (!token) redirect("/ingresar");

  let publicacion;
  try {
    publicacion = await miPublicacion(token, id);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }
  const catalogo = await catalogoAlta();

  return (
    <>
      <Encabezado />
      <main className={estilos.pagina}>
        <EditorPublicacion
          inicial={publicacion}
          catalogo={catalogo}
          puedePublicar={cuenta.prestador.puede_publicar}
        />
      </main>
    </>
  );
}
