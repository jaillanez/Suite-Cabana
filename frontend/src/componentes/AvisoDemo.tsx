import { Alerta } from "./Iconos";
import estilos from "./AvisoDemo.module.css";

/* Mientras la oferta sea la semilla de desarrollo, la pantalla lo dice: en los
   resultados y también cuando no hay ninguno, que es donde la copia afirma cosas
   sobre la oferta del destino. Un alojamiento de ejemplo no puede pasar por uno
   real ni por un descuido.

   Pero hay dos cosas distintas y decirlas igual sería mentir en la otra
   dirección. Un alojamiento inventado es de ejemplo de punta a punta. Los Búhos
   existe: el lugar, las fotos y los servicios son suyos, y lo único provisorio
   son las unidades, los precios y la dirección exacta. Llamarlo «datos de
   ejemplo» y decir que sus fotos salieron de un banco de imágenes desmerece un
   lugar real. */
export default function AvisoDemo({
  variante = "ejemplo",
}: {
  variante?: "ejemplo" | "provisorio";
}) {
  return (
    <p className={estilos.aviso}>
      <Alerta className={estilos.icono} />
      {variante === "provisorio" ? (
        <span>
          <strong>Datos provisorios.</strong> El lugar, las fotos y los servicios son
          reales. Lo que falta confirmar con el dueño son las unidades, los precios y la
          dirección exacta, así que todavía no se puede reservar con estos números.
        </span>
      ) : (
        <span>
          <strong>Datos de ejemplo.</strong> Los alojamientos, precios, disponibilidad y
          todos los contadores de esta página son de prueba; las localidades son reales y
          las fotos son de Wikimedia Commons con licencia libre. Todavía no hay prestadores
          publicando.
        </span>
      )}
    </p>
  );
}
