"""Datos de la semilla de desarrollo.

Provincias, departamentos y distritos son datos públicos reales, con coordenadas
aproximadas de la cabecera de cada departamento (sirven para el mapa y para la
distancia al centro). Los prestadores, publicaciones y unidades son FICTICIOS y
se marcan con `es_demo` en la base: ningún nombre inventado debe poder
confundirse con un negocio real.

La oferta de ejemplo está centrada en la provincia de San Juan, con el
departamento Rivadavia como foco.
"""

from decimal import Decimal as D

PROVINCIAS = [
    ("Buenos Aires", "buenos-aires"),
    ("Catamarca", "catamarca"),
    ("Chaco", "chaco"),
    ("Chubut", "chubut"),
    ("Ciudad Autónoma de Buenos Aires", "caba"),
    ("Córdoba", "cordoba"),
    ("Corrientes", "corrientes"),
    ("Entre Ríos", "entre-rios"),
    ("Formosa", "formosa"),
    ("Jujuy", "jujuy"),
    ("La Pampa", "la-pampa"),
    ("La Rioja", "la-rioja"),
    ("Mendoza", "mendoza"),
    ("Misiones", "misiones"),
    ("Neuquén", "neuquen"),
    ("Río Negro", "rio-negro"),
    ("Salta", "salta"),
    ("San Juan", "san-juan"),
    ("San Luis", "san-luis"),
    ("Santa Cruz", "santa-cruz"),
    ("Santa Fe", "santa-fe"),
    ("Santiago del Estero", "santiago-del-estero"),
    ("Tierra del Fuego", "tierra-del-fuego"),
    ("Tucumán", "tucuman"),
]

# Departamentos de San Juan: (provincia, nombre, slug, lat, lon, publicaciones,
# perfil de temporada, distritos). Coordenadas aproximadas de la cabecera.
LOCALIDADES = [
    # Gran San Juan. Rivadavia concentra la oferta de ejemplo.
    (
        "san-juan", "Rivadavia", "rivadavia", -31.5333, -68.5833, 9, "valle",
        ["Marquesado", "La Bebida", "Quebrada de Zonda", "Meglioli", "Undiano"],
    ),
    (
        "san-juan", "Capital", "capital-san-juan", -31.5375, -68.5364, 5, "valle",
        ["Centro", "Desamparados", "Trinidad", "Concepción"],
    ),
    (
        "san-juan", "Rawson", "rawson", -31.5833, -68.5333, 5, "valle",
        ["Villa Krause", "Médano de Oro", "Villa Bolaños", "Villa Centenario"],
    ),
    (
        "san-juan", "Santa Lucía", "santa-lucia", -31.5333, -68.4833, 2, "valle",
        ["Villa Santa Lucía", "Colonia Sarmiento"],
    ),
    (
        "san-juan", "Chimbas", "chimbas", -31.4833, -68.5333, 2, "valle",
        ["Villa Paula", "El Mogote"],
    ),
    (
        "san-juan", "Pocito", "pocito", -31.6667, -68.5833, 3, "valle",
        ["Villa Aberastain", "Carpintería", "La Rinconada"],
    ),
    (
        "san-juan", "Albardón", "albardon", -31.4333, -68.4833, 2, "valle",
        ["Campo Afuera", "Las Lomitas"],
    ),
    (
        "san-juan", "Caucete", "caucete", -31.6500, -68.2833, 2, "valle",
        ["Vallecito", "Bermejo", "Pie de Palo"],
    ),
    (
        "san-juan", "9 de Julio", "nueve-de-julio", -31.5333, -68.3667, 1, "valle",
        ["Villa Santa Rosa"],
    ),
    ("san-juan", "Angaco", "angaco", -31.4333, -68.3833, 1, "valle", ["Villa El Salvador"]),
    (
        "san-juan", "San Martín", "san-martin", -31.4333, -68.3333, 1, "valle",
        ["Villa Dominguito"],
    ),
    (
        "san-juan", "25 de Mayo", "veinticinco-de-mayo", -31.7167, -68.2833, 1, "valle",
        ["Santa Rosa"],
    ),
    (
        "san-juan", "Sarmiento", "sarmiento", -31.9833, -68.4167, 2, "valle",
        ["Media Agua", "Cienaguita", "Los Berros"],
    ),
    # Quebradas y diques, a media hora del centro.
    (
        "san-juan", "Zonda", "zonda", -31.5333, -68.7000, 3, "quebrada",
        ["Villa Basilio Nievas", "Quebrada de Zonda"],
    ),
    (
        "san-juan", "Ullum", "ullum", -31.4500, -68.6667, 3, "quebrada",
        ["Villa Ibáñez", "Dique de Ullum", "Las Tapias"],
    ),
    # Destinos de montaña y de parque.
    (
        "san-juan", "Calingasta", "calingasta", -31.3333, -69.4167, 5, "montana",
        ["Barreal", "Tamberías", "Villa Calingasta", "Sorocayense"],
    ),
    (
        "san-juan", "Iglesia", "iglesia", -30.2167, -69.1333, 4, "montana",
        ["Rodeo", "Las Flores", "Pismanta", "Bella Vista", "Angualasto"],
    ),
    (
        "san-juan", "Valle Fértil", "valle-fertil", -30.6333, -67.4667, 4, "parque",
        ["San Agustín del Valle Fértil", "Usno", "Chucuma", "Astica"],
    ),
    (
        "san-juan", "Jáchal", "jachal", -30.2333, -68.7500, 3, "norte",
        ["San José de Jáchal", "Huaco", "El Médano", "Pampa Vieja"],
    ),
]

TIPOS_SERVICIO = [
    ("alojamiento", "Alojamiento", "noches"),
    ("excursion", "Excursión", "turno_cupo"),
    ("gastronomia", "Gastronomía", "horario"),
    ("traslado", "Traslado", "tramo"),
    # docs/04: por franja fija o por horas, con disponibilidad por rango de hora.
    ("salon_eventos", "Salón de eventos", "horas"),
]

# (tipo de servicio, código, nombre)
SUBTIPOS = [
    ("alojamiento", "cabana", "Cabaña"),
    ("alojamiento", "casa", "Casa"),
    ("alojamiento", "departamento", "Departamento"),
    ("alojamiento", "hosteria", "Hostería"),
    ("alojamiento", "hotel", "Hotel"),
    ("alojamiento", "bungalow", "Bungalow"),
    ("salon_eventos", "salon_eventos", "Salón"),
    ("salon_eventos", "quincho_eventos", "Quincho"),
    ("salon_eventos", "aire_libre", "Espacio al aire libre"),
]

A = ("alojamiento",)
S = ("salon_eventos",)
AS = ("alojamiento", "salon_eventos")

# (código, nombre, ícono, tipos de servicio a los que aplica)
COMODIDADES = [
    ("wifi", "WiFi", "wifi", AS),
    ("pileta", "Pileta", "pileta", AS),
    ("mascotas", "Acepta mascotas", "mascota", A),
    ("cochera", "Cochera", "auto", A),
    ("parrilla", "Parrilla", "parrilla", AS),
    ("aire", "Aire acondicionado", "aire", AS),
    ("calefaccion", "Calefacción", "calefaccion", AS),
    ("desayuno", "Desayuno incluido", "desayuno", A),
    ("lavarropas", "Lavarropas", "lavarropas", A),
    ("tv", "TV por cable", "tv", A),
    ("ropa_blanca", "Ropa blanca incluida", "cama", A),
    ("accesible", "Accesible en silla de ruedas", "accesible", AS),
    # En una cabaña dicen "el complejo tiene salón / quincho"; el salón en sí se
    # publica aparte, como su propio tipo de servicio.
    ("salon", "Salón de eventos", "salon", A),
    ("quincho", "Quincho", "quincho", A),
    # Propias de salones.
    ("estacionamiento", "Estacionamiento", "auto", S),
    ("sonido", "Equipo de sonido", "sonido", S),
    ("pista", "Pista de baile", "pista", S),
    ("mesas_sillas", "Mesas y sillas", "mesa", S),
    ("cocina", "Cocina equipada", "cocina", S),
    ("vajilla", "Vajilla", "vajilla", S),
    ("escenario", "Escenario", "escenario", S),
    ("proyector", "Proyector y pantalla", "proyector", S),
    ("grupo_electrogeno", "Grupo electrógeno", "energia", S),
    ("juegos_infantiles", "Juegos infantiles", "juegos", S),
    ("banos_accesibles", "Baños accesibles", "accesible", S),
]

# Publicación destacada: un lugar REAL, cargado aparte de la oferta generada.
# Solo lleva los datos verificados; lo que falta está anotado y se completa
# cuando el prestador lo aporte. Ver `PENDIENTES_LOS_BUHOS`.
LOS_BUHOS = {
    "titulo": "Los Búhos",
    "slug": "los-buhos-medano-de-oro",
    "localidad": "rawson",
    "zona": "Médano de Oro",
    # Exactas, del punto del lugar en Google Maps.
    "lat": -31.612543,
    "lon": -68.463775,
    "subtipo": "cabana",
    # Las palabras son del prestador, de su propio anuncio. Describir su lugar
    # mejor de lo que lo describe él sería inventar.
    "descripcion": (
        "Un rincón pensado para desconectar y disfrutar. Rodeado de verde, árboles y "
        "tranquilidad, nuestro loft combina la calidez de lo rústico con la comodidad "
        "que necesitás para descansar, compartir y crear lindos recuerdos. Un lugar "
        "simple, acogedor y especial para sentirte lejos de todo, sin dejar de sentirte "
        "como en casa.\n\n"
        "Espacios verdes, mangrullo, juego de plaza, metegol, pileta para adultos y "
        "niños, y parrillero con horno chileno."
    ),
    "comodidades": [
        "wifi", "aire", "calefaccion", "mascotas",
        "pileta", "parrilla", "cochera", "tv", "salon",
    ],
    "confirmacion_inmediata": False,
    # Una sola unidad: un loft. Un dormitorio con cama doble, dos de una plaza y
    # una hamaca paraguaya; un baño.
    "unidades": [
        {
            "nombre": "Loft",
            "capacidad": 5,
            "capacidad_base": 5,
            # Derivado del total que Airbnb le cobra al viajero por 3 noches
            # ($200.612 antes de su promoción de anuncio nuevo). Queda igualado
            # para que el mismo lugar no cueste distinto según dónde se reserve.
            # PROVISORIO hasta que el prestador confirme su tarifa.
            "precio_noche": D(66900),
            "estadia_minima": 2,
        }
    ],
}

# Lo que falta para que Los Búhos deje de ser provisorio. Mientras esté acá,
# la publicación queda marcada como dato de ejemplo.
PENDIENTES_LOS_BUHOS = [
    "Confirmar la tarifa por noche: la de acá se dedujo del total de Airbnb, que "
    "incluye las comisiones de ellos y no se puede separar desde afuera",
    "¿Cobra limpieza o persona extra? Hoy van en cero",
    "Capacidad: acá dice 5 personas y en Airbnb dice 4 — conviene que coincidan",
]

# El salón de Los Búhos (docs/04, etapa 7). Queda en BORRADOR: de él solo se sabe
# lo que muestran las fotos. Capacidad, turnos, precios y seña son del prestador;
# inventarlos sería publicar una oferta que nadie hizo. Él los completa desde su
# panel, con el mismo editor que cualquier anfitrión.
LOS_BUHOS_SALON = {
    "titulo": "Salón Los Búhos",
    "slug": "los-buhos-salon-medano-de-oro",
    "subtipo": "salon_eventos",
    "politica": "eventos",
    # Lo único que se ve sin dudas en las fotos. El resto (aire, cocina, parrilla)
    # puede estar o no: lo confirma él.
    "comodidades": ["mesas_sillas"],
    # En `fotos/los-buhos/salon/`. Orden explícito: los nombres no vienen numerados
    # y el alfabético pondría el baño antes que el salón.
    "fotos": [
        "salon Interior 1.jpeg",
        "Salon interior 2.jpeg",
        "Salon interior 3.jpeg",
        "Salon interior 4.jpeg",
        "baño damas.jpeg",
    ],
}

# Lo que tiene que aportar el prestador para publicar el salón.
PENDIENTES_SALON_LOS_BUHOS = [
    "Capacidad con todos sentados y de pie (en las fotos hay mesa para unas 40 personas)",
    "Cómo lo alquila: turnos fijos (nombre, horario, precio) y/o por hora (precio, "
    "mínimo de horas, horario de atención)",
    "Seña: qué porcentaje cobra al reservar",
    "Tiempo de preparación o limpieza entre eventos",
    "Adicionales con precio (vajilla, limpieza, sonido…) y reglas (música hasta qué "
    "hora, catering propio, decoración)",
    "Descripción del salón, en sus palabras",
    "Comodidades: confirmar aire acondicionado, cocina, parrilla y estacionamiento",
]

# Porcentajes PROVISORIOS: docs/01 §9 los marca como decisión pendiente de Dirección.
POLITICAS = [
    (
        "flexible",
        "Flexible",
        "Provisoria: los porcentajes y plazos definitivos están pendientes (docs/01 §9).",
        [
            {"dias_antes": 1, "porcentaje_reintegro": 100},
            {"dias_antes": 0, "porcentaje_reintegro": 50},
        ],
    ),
    (
        "moderada",
        "Moderada",
        "Provisoria: los porcentajes y plazos definitivos están pendientes (docs/01 §9).",
        [
            {"dias_antes": 7, "porcentaje_reintegro": 100},
            {"dias_antes": 2, "porcentaje_reintegro": 50},
        ],
    ),
    (
        "estricta",
        "Estricta",
        "Provisoria: los porcentajes y plazos definitivos están pendientes (docs/01 §9).",
        [
            {"dias_antes": 30, "porcentaje_reintegro": 100},
            {"dias_antes": 14, "porcentaje_reintegro": 50},
        ],
    ),
    (
        "eventos",
        "Eventos",
        # Decidido con Dirección (docs/04 §2): nunca el 100 %, el 10 % de lo
        # pagado queda siempre una vez confirmada y señada la fecha.
        "Hasta 30 días antes se devuelve el 90 % de lo pagado; hasta 15 días antes, "
        "el 50 %; después, nada.",
        [
            {"dias_antes": 30, "porcentaje_reintegro": 90},
            {"dias_antes": 15, "porcentaje_reintegro": 50},
        ],
    ),
]

PRESTADORES = [
    "Turismo del Zonda S.R.L.",
    "Fincas de Cuyo S.A.",
    "Hospedajes del Tulum S.R.L.",
    "Sol y Viña Alojamientos S.R.L.",
    "Cordillera Anfitriona S.A.",
    "Casa de Adobe Turismo S.R.L.",
    "Valle del Sol Hospedajes S.R.L.",
    "Los Algarrobos Turismo S.A.",
    "Marquesado Alojamientos S.R.L.",
    "Sierra Chica Hospedar S.R.L.",
    "Dique y Monte S.R.L.",
    "Barreal Recibe S.A.",
    "Ischigualasto Anfitriones S.R.L.",
    "Norte Sanjuanino Turismo S.R.L.",
    "La Acequia Alojamientos S.R.L.",
    "Piedra Pintada Hospedajes S.A.",
]

PREFIJOS = [
    "Finca", "Cabañas", "Casa", "Posada", "Hostería", "Departamentos",
    "Complejo", "Refugio", "Solar", "Rincón",
]
NOMBRES = [
    "Los Olivos", "del Zonda", "Las Vides", "El Algarrobo", "La Acequia",
    "Los Chañares", "del Dique", "La Bodega", "El Molle", "Las Tapias",
    "de la Quebrada", "Los Jarillales", "El Retamo", "La Huerta", "del Tulum",
    "Los Membrillos", "La Ciénaga", "El Pedernal", "Las Higueras", "del Médano",
    "Los Nogales", "La Majadita", "El Sarmiento", "Las Lomitas",
]

UNIDADES = [
    ("Cabaña 1", 4), ("Cabaña 2", 4), ("Cabaña 3", 6), ("Cabaña 4", 2),
    ("Departamento A", 3), ("Departamento B", 5), ("Casa principal", 8),
    ("Suite del fondo", 2), ("Loft", 2), ("Bungalow chico", 3),
]

# Precio base por noche según perfil de destino, en pesos.
PRECIO_BASE = {
    "valle": (D("38000"), D("86000")),
    "quebrada": (D("45000"), D("98000")),
    "montana": (D("55000"), D("132000")),
    "parque": (D("42000"), D("96000")),
    "norte": (D("35000"), D("78000")),
}

# (nombre, desde, hasta, recargo) por perfil. Ciclo 2026-2027.
TEMPORADAS = {
    "valle": [
        ("Fiesta Nacional del Sol", (2027, 2, 19), (2027, 3, 1), D("1.45")),
        ("Vendimia y cosecha", (2027, 3, 1), (2027, 3, 20), D("1.25")),
    ],
    "quebrada": [("Temporada de verano", (2026, 12, 15), (2027, 3, 1), D("1.30"))],
    "montana": [
        ("Temporada de verano", (2026, 12, 15), (2027, 3, 1), D("1.35")),
        ("Vacaciones de invierno", (2027, 7, 8), (2027, 7, 27), D("1.25")),
    ],
    "parque": [
        ("Semana Santa", (2027, 3, 24), (2027, 3, 29), D("1.50")),
        ("Vacaciones de invierno", (2027, 7, 8), (2027, 7, 27), D("1.30")),
    ],
    "norte": [("Temporada de verano", (2026, 12, 15), (2027, 2, 28), D("1.25"))],
}

DESCRIPCIONES = [
    "A pocos minutos del centro de San Juan, con parral, galería y estacionamiento en el predio.",
    "Casa de adobe y caña, fresca en verano, rodeada de olivos y con parrilla propia.",
    "Alojamiento tranquilo entre viñedos, pensado para quienes vienen a recorrer bodegas.",
    "Vista abierta a la Sierra Chica desde la galería, con pileta y espacio verde común.",
    "Sobre calle interna sin tránsito, a diez minutos de la Quebrada de Zonda.",
    "Complejo chico atendido por sus dueños, con quincho, pileta y aire en todas las unidades.",
    "Unidades independientes con cocina completa, ropa blanca y cochera techada.",
    "A media hora del dique, ideal para quienes llegan en auto y salen temprano.",
    "Casa de campo con parral, horno de barro y sombra de morera; buena base para Ischigualasto.",
    "Construcción en piedra y adobe, con calefacción a leña para las noches de la cordillera.",
]

REGLAS_CASA = [
    "Ingreso desde las 14, salida hasta las 10. No se permiten fiestas.",
    "Se aceptan mascotas pequeñas avisando al reservar. No se fuma dentro de las unidades.",
    "Silencio de 23 a 8. La pileta se usa de 9 a 20 bajo responsabilidad del huésped.",
    "Ingreso desde las 15, salida hasta las 10. Estacionamiento para un vehículo por unidad.",
]
