import type { EstadoReserva } from "@/lib/api";
import estilos from "./EstadoReserva.module.css";

const TEXTOS: Record<EstadoReserva, { nombre: string; explica: string }> = {
  pendiente_pago: {
    nombre: "Esperando el pago",
    explica: "Te guardamos el lugar un rato. Si no pagás, se libera solo.",
  },
  pendiente_aprobacion: {
    nombre: "Esperando al prestador",
    explica: "Pagaste. El prestador tiene un plazo para aceptar o rechazar.",
  },
  confirmada: { nombre: "Confirmada", explica: "Está todo listo. Te esperan esas fechas." },
  cancelada: { nombre: "Cancelada", explica: "Las fechas quedaron liberadas." },
  completada: { nombre: "Completada", explica: "Ya pasó la estadía." },
  en_reclamo: { nombre: "En reclamo", explica: "Hay un reclamo abierto sobre esta reserva." },
};

export default function Estado({
  estado,
  conExplicacion = false,
}: {
  estado: EstadoReserva;
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

export { TEXTOS as TEXTOS_RESERVA };
