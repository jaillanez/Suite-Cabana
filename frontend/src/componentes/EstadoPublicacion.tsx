import type { EstadoPublicacion } from "@/lib/api";
import estilos from "./EstadoPublicacion.module.css";

const TEXTOS: Record<EstadoPublicacion, { nombre: string; explica: string }> = {
  borrador: { nombre: "Borrador", explica: "Solo la ves vos. Completala y mandala a revisión." },
  en_revision: {
    nombre: "En revisión",
    explica: "La está mirando un operador. Mientras tanto no se puede editar.",
  },
  aprobada: { nombre: "Publicada", explica: "Se ve en las búsquedas y se puede reservar." },
  pausada: { nombre: "Pausada", explica: "No aparece en las búsquedas. La reactivás cuando quieras." },
  rechazada: { nombre: "Rechazada", explica: "Corregí lo que te marcaron y volvé a mandarla." },
};

export default function Estado({
  estado,
  conExplicacion = false,
}: {
  estado: EstadoPublicacion;
  conExplicacion?: boolean;
}) {
  const texto = TEXTOS[estado];
  return (
    <span className={`${estilos.estado} ${estilos[estado]}`}>
      <span className={estilos.punto} aria-hidden="true" />
      {texto.nombre}
      {conExplicacion && <span className={estilos.explica}>{texto.explica}</span>}
    </span>
  );
}

export { TEXTOS as TEXTOS_ESTADO };
