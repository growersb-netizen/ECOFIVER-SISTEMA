"""
Fichas de producto pre-escritas para publicaciones de MercadoLibre.
Cada ficha tiene:
  - titulo_ml : título optimizado para el buscador de ML (máx 60 chars, sin palabras de relleno)
  - descripcion_ml : descripción del producto específico (300-400 palabras, texto plano)

El encabezado, pie y palabras clave de empresa se agregan aparte desde la configuración ML.
Para editar: modificar este archivo y hacer git push → Railway redeploya automáticamente.
"""

FICHAS_PISCINAS: dict = {

    # ─── MINIDECK ──────────────────────────────────────────────────────────────
    "Minideck": {
        "titulo_ml": "Pileta fibra de vidrio 3x2 metros con deck plataforma",
        "atributos_ml": {"BRAND": "EcoFiver", "MATERIAL": "Fibra de vidrio",
                         "LENGTH": "300", "WIDTH": "200", "DEPTH": "70", "CAPACITY": "4200"},
        "descripcion_ml": (
            "Pileta Minideck de fibra de vidrio de 3 metros de largo por 2 metros de ancho, "
            "con profundidad uniforme de 0,70 metros. Ideal para espacios reducidos, patios "
            "pequeños y uso familiar con niños. Capacidad de 4.200 litros.\n\n"
            "La piscina Minideck incorpora una plataforma lateral integrada que permite el "
            "ingreso cómodo y amplía el espacio de disfrute alrededor del agua. El casco de "
            "fibra de vidrio es de fabricación propia, con laminado de alta resistencia que "
            "garantiza durabilidad ante las condiciones climáticas de Buenos Aires y el interior "
            "del país.\n\n"
            "La fibra de vidrio no requiere pintura periódica, es impermeable, no absorbe "
            "algas y tiene superficie lisa que facilita la limpieza. A diferencia de las piletas "
            "de hormigón o vinilo, no se fisura ni necesita mantenimiento estructural.\n\n"
            "Medidas exteriores: 3,00 m de largo × 2,00 m de ancho × 0,70 m de profundidad. "
            "La instalación incluye nivelación del terreno, conexión hidráulica y puesta en "
            "marcha del sistema de filtrado. No requiere obras de albañilería.\n\n"
            "Fabricada en Zárate, Buenos Aires. Instalación a cargo de nuestro equipo en zona "
            "de cobertura. Consultar disponibilidad de envío e instalación antes de comprar. "
            "Financiación propia disponible en cuotas."
        ),
    },

    "Minideck Chico": {
        "titulo_ml": "Pileta fibra de vidrio 3x2 metros con deck plataforma",
        "atributos_ml": {"BRAND": "EcoFiver", "MATERIAL": "Fibra de vidrio",
                         "LENGTH": "300", "WIDTH": "200", "DEPTH": "70", "CAPACITY": "4200"},
        "descripcion_ml": (
            "Pileta Minideck Chico de fibra de vidrio, 3 metros de largo por 2 metros de ancho "
            "y profundidad uniforme de 0,70 metros. Capacidad aproximada de 4.200 litros. "
            "Piscina compacta para espacios reducidos y familias con niños pequeños.\n\n"
            "El modelo Minideck incorpora una plataforma integrada que funciona como zona de "
            "descanso y facilita el ingreso al agua. La piscina es fabricada en fibra de vidrio "
            "de alta resistencia, material que no requiere pintura, no absorbe algas y se limpia "
            "con facilidad. Durabilidad garantizada ante el clima argentino.\n\n"
            "La instalación incluye nivelación del terreno, conexión hidráulica y puesta en "
            "marcha. Sin obras de albañilería. Instalación a cargo de nuestro equipo técnico "
            "en zona de cobertura (consultar antes de comprar).\n\n"
            "Medidas: 3,00 m × 2,00 m × 0,70 m de profundidad. Fabricación propia en Zárate, "
            "Buenos Aires. Financiación en cuotas disponible. Consultar por flete e instalación "
            "antes de ofertar."
        ),
    },

    "Minideck Grande": {
        "titulo_ml": "Pileta fibra de vidrio 3x2 metros deck plataforma grande",
        "atributos_ml": {"BRAND": "EcoFiver", "MATERIAL": "Fibra de vidrio",
                         "LENGTH": "300", "WIDTH": "200", "DEPTH": "70", "CAPACITY": "4200"},
        "descripcion_ml": (
            "Pileta Minideck Grande de fibra de vidrio, 3 metros de largo por 2 metros de ancho "
            "y profundidad de 0,70 metros. Capacidad de 4.200 litros. Diseño compacto con "
            "plataforma integrada de mayor superficie para comodidad del usuario.\n\n"
            "El casco de fibra de vidrio de fabricación propia tiene laminado reforzado, "
            "resistente a los rayos UV y a los productos de tratamiento del agua. No requiere "
            "pintura ni mantenimiento estructural. Superficie interna lisa que dificulta la "
            "proliferación de algas y bacterias.\n\n"
            "Ideal como piscina familiar, pileta de terraza o natatorio para espacios chicos. "
            "Se instala sin obra de albañilería. La instalación incluye nivelación del terreno, "
            "conexión del sistema de filtrado y prueba de funcionamiento.\n\n"
            "Fabricada en Zárate, Buenos Aires. Consultar flete e instalación según zona. "
            "Financiación propia en cuotas."
        ),
    },

    # ─── MINIPORTANTE / AUTOPORTANTE ───────────────────────────────────────────
    "Miniportante": {
        "titulo_ml": "Pileta autoportante fibra de vidrio 2.5x2 metros sin excavar",
        "atributos_ml": {"BRAND": "EcoFiver", "MATERIAL": "Fibra de vidrio",
                         "LENGTH": "250", "WIDTH": "210", "DEPTH": "70", "CAPACITY": "3675"},
        "descripcion_ml": (
            "Pileta Miniportante de fibra de vidrio, 2,50 metros de largo por 2,10 metros de "
            "ancho y 0,70 metros de profundidad. Capacidad de 3.675 litros. Modelo autoportante "
            "que se instala sin necesidad de excavar ni realizar obra.\n\n"
            "La piscina Miniportante es ideal para patios pequeños, balcones amplios, terrazas "
            "y espacios con piso firme donde no es posible hacer excavación. El casco de fibra "
            "de vidrio tiene estructura autoportante que no requiere muros ni contención lateral.\n\n"
            "La fibra de vidrio no absorbe humedad, no se fisura, no necesita pintura y es "
            "químicamente resistente al cloro y otros productos de tratamiento. Fácil limpieza "
            "con superficie interna vitrificada.\n\n"
            "Medidas: 2,50 m × 2,10 m × 0,70 m de profundidad. No requiere excavación ni "
            "albañilería. Instalación incluida en zona de cobertura. Consultar disponibilidad "
            "antes de ofertar. Fabricada en Zárate, Buenos Aires. Financiación en cuotas."
        ),
    },

    "Autoportante": {
        "titulo_ml": "Pileta autoportante fibra de vidrio 4x2 metros sin excavar",
        "atributos_ml": {"BRAND": "EcoFiver", "MATERIAL": "Fibra de vidrio",
                         "LENGTH": "410", "WIDTH": "210", "DEPTH": "70", "CAPACITY": "6027"},
        "descripcion_ml": (
            "Piscina Autoportante de fibra de vidrio, 4,10 metros de largo por 2,10 metros de "
            "ancho y 0,70 metros de profundidad. Capacidad de 6.027 litros. Instalación sin "
            "excavación ni obra de albañilería.\n\n"
            "El modelo Autoportante tiene un casco de fibra de vidrio con estructura rígida "
            "que se sostiene solo, ideal para colocar sobre terrenos firmes, terrazas, patios "
            "de hormigón o decks de madera. A diferencia de las piletas inflables o de armazón "
            "metálico, la fibra de vidrio es duradera, resistente al sol y no se deteriora con "
            "el uso continuado.\n\n"
            "Pileta de natación compacta para uso familiar, perfecta como natatorio de "
            "entrenamiento o recreación. La profundidad uniforme de 0,70 m la hace segura "
            "para niños y adultos.\n\n"
            "Instalación incluida. No requiere excavación ni obras. Fabricada en Zárate, "
            "Buenos Aires. Consultar zona de instalación y flete antes de ofertar. "
            "Financiación en cuotas."
        ),
    },

    # ─── ARCO ROMANO CHICO ─────────────────────────────────────────────────────
    "Arco Romano Chico Recto": {
        "titulo_ml": "Piscina arco romano fibra de vidrio 4.6x2.47 metros 1.20m",
        "atributos_ml": {"BRAND": "EcoFiver", "MATERIAL": "Fibra de vidrio",
                         "LENGTH": "460", "WIDTH": "247", "DEPTH": "120", "CAPACITY": "13625"},
        "descripcion_ml": (
            "Pileta Arco Romano Chico Recto de fibra de vidrio, 4,60 metros de largo por "
            "2,47 metros de ancho y 1,20 metros de profundidad uniforme. Capacidad de "
            "13.625 litros. Diseño clásico con arcos curvos en los extremos que aportan "
            "elegancia y optimizan el espacio interior.\n\n"
            "La forma de arco romano permite aprovechar mejor el volumen de agua respecto "
            "a las piletas rectangulares del mismo largo, con extremos curvos que facilitan "
            "el giro al nadar y dan un aspecto más sofisticado al jardín o patio.\n\n"
            "El casco de fibra de vidrio es fabricado en Zárate, Buenos Aires, con laminado "
            "de poliéster reforzado y gelcoat de primera calidad. Resistente a rayos UV, "
            "productos químicos de tratamiento y condiciones climáticas extremas. No requiere "
            "pintura ni mantenimiento estructural.\n\n"
            "Medidas: 4,60 m de largo × 2,47 m de ancho × 1,20 m de profundidad. La "
            "profundidad de 1,20 m permite nadar con comodidad. Instalación incluida: "
            "excavación, colocación, conexión hidráulica y puesta en marcha del filtro. "
            "Consultar por flete e instalación según zona antes de ofertar."
        ),
    },

    "Arco Romano Chico C/Desnivel": {
        "titulo_ml": "Piscina arco romano fibra de vidrio 4.6x2.35 metros con desnivel",
        "atributos_ml": {"BRAND": "EcoFiver", "MATERIAL": "Fibra de vidrio",
                         "LENGTH": "460", "WIDTH": "235", "DEPTH": "110", "CAPACITY": "12972"},
        "descripcion_ml": (
            "Pileta Arco Romano Chico con Desnivel de fibra de vidrio, 4,60 metros de largo "
            "por 2,35 metros de ancho. Profundidad variable: 1,10 metros en la zona de playa "
            "y 1,30 metros en la zona de nado. Capacidad de 12.972 litros.\n\n"
            "El desnivel en el fondo crea dos zonas bien diferenciadas: una parte más baja "
            "para niños y zona de recreación, y una parte más profunda para adultos y nado. "
            "Es la opción más completa del modelo Arco Romano Chico.\n\n"
            "Casco de fibra de vidrio fabricado con laminado de alta resistencia. Arcos "
            "curvos en ambos extremos que dan un aspecto premium y optimizan el espacio. "
            "Superficie interna vitrificada: fácil limpieza, sin porosidades, sin algas.\n\n"
            "Medidas: 4,60 m × 2,35 m, profundidad 1,10-1,30 m. Instalación incluida "
            "(excavación, nivelación, conexión hidráulica). Fabricada en Zárate, Buenos Aires. "
            "Consultar zona de instalación y flete antes de comprar. Financiación en cuotas."
        ),
    },

    "Arco Romano Chico Curvo": {
        "titulo_ml": "Piscina arco romano curvo fibra de vidrio 4.6x2.35 metros",
        "atributos_ml": {"BRAND": "EcoFiver", "MATERIAL": "Fibra de vidrio",
                         "LENGTH": "460", "WIDTH": "235", "DEPTH": "110", "CAPACITY": "12972"},
        "descripcion_ml": (
            "Pileta Arco Romano Chico Curvo de fibra de vidrio, 4,60 metros de largo por "
            "2,35 metros de ancho. Profundidad de 1,10 a 1,30 metros. Capacidad de 12.972 litros. "
            "Diseño con arcos curvos en extremos y laterales para un perfil más redondeado.\n\n"
            "La versión Curvo del Arco Romano Chico tiene un perfil más orgánico y suave que "
            "la versión Recto, ideal para jardines de diseño contemporáneo o rústico. El fondo "
            "con leve desnivel distingue la zona de playa (más baja) de la zona de nado.\n\n"
            "Fabricada en fibra de vidrio de alta resistencia con gelcoat de primera calidad "
            "en Zárate, Buenos Aires. Sin mantenimiento estructural, sin pintura, sin fisuras. "
            "Instalación incluida. Consultar zona de cobertura antes de ofertar."
        ),
    },

    # ─── ARCO ROMANO MEDIANO ───────────────────────────────────────────────────
    "Arco Romano Mediano Recto": {
        "titulo_ml": "Piscina arco romano 6.40x2.94 metros fibra de vidrio 1.40m",
        "atributos_ml": {"BRAND": "EcoFiver", "MATERIAL": "Fibra de vidrio",
                         "LENGTH": "640", "WIDTH": "294", "DEPTH": "140", "CAPACITY": "26342"},
        "descripcion_ml": (
            "Pileta Arco Romano Mediano Recto de fibra de vidrio, 6,40 metros de largo por "
            "2,94 metros de ancho y 1,40 metros de profundidad uniforme. Capacidad de "
            "26.342 litros. La piscina más elegante y completa de la línea media: combina "
            "largo de nado real con la estética clásica del arco romano.\n\n"
            "Con 6,40 metros de largo y 1,40 metros de profundidad, esta pileta permite nadar "
            "a crawl y espalda sin restricciones. Los arcos curvos en los extremos optimizan "
            "el diseño y le dan un aspecto premium al jardín o espacio exterior.\n\n"
            "El casco está fabricado en fibra de vidrio con laminado de poliéster reforzado "
            "y gelcoat UV de alta calidad. No requiere pintura ni mantenimiento estructural. "
            "La superficie vitrificada interna dificulta el crecimiento de algas y facilita "
            "la limpieza con una simple pasada del cepillo.\n\n"
            "Medidas: 6,40 m × 2,94 m × 1,40 m de profundidad. Instalación incluida: "
            "excavación, colocación del casco, conexión hidráulica y puesta en marcha del "
            "sistema de filtrado. Fabricada en Zárate, Buenos Aires. Consultar flete e "
            "instalación por zona antes de ofertar. Financiación en cuotas disponible."
        ),
    },

    "Arco Romano Mediano C/Desnivel": {
        "titulo_ml": "Piscina arco romano 7x3.35 metros fibra de vidrio con desnivel",
        "atributos_ml": {"BRAND": "EcoFiver", "MATERIAL": "Fibra de vidrio",
                         "LENGTH": "700", "WIDTH": "335", "DEPTH": "125", "CAPACITY": "34617"},
        "descripcion_ml": (
            "Pileta Arco Romano Mediano con Desnivel de fibra de vidrio, 7,00 metros de largo "
            "por 3,35 metros de ancho. Profundidad variable: 1,25 metros en zona de playa y "
            "1,70 metros en zona de nado. Capacidad de 34.617 litros.\n\n"
            "El tamaño de 7 metros de largo y 3,35 metros de ancho convierte a esta piscina "
            "en una natatorio familiar de primer nivel. La diferencia de profundidad entre "
            "la zona de playa y la zona de nado (1,25 a 1,70 m) permite un uso simultáneo "
            "seguro para niños y adultos.\n\n"
            "Casco de fibra de vidrio de alta resistencia, fabricado en Zárate, Buenos Aires. "
            "Arcos curvos en los extremos, diseño elegante para jardines amplios. Sin "
            "mantenimiento estructural. La instalación incluye excavación, nivelación, "
            "colocación y conexión hidráulica completa.\n\n"
            "Medidas: 7,00 m × 3,35 m, profundidad 1,25-1,70 m. Consultar zona de instalación "
            "y flete antes de ofertar. Financiación en cuotas propia disponible."
        ),
    },

    "Arco Romano Mediano Curvo": {
        "titulo_ml": "Piscina arco romano curvo 7x3.35 metros fibra de vidrio",
        "atributos_ml": {"BRAND": "EcoFiver", "MATERIAL": "Fibra de vidrio",
                         "LENGTH": "700", "WIDTH": "335", "DEPTH": "125", "CAPACITY": "34617"},
        "descripcion_ml": (
            "Pileta Arco Romano Mediano Curvo de fibra de vidrio, 7,00 metros de largo por "
            "3,35 metros de ancho. Profundidad variable de 1,25 a 1,70 metros. Capacidad de "
            "34.617 litros. Perfil orgánico y redondeado en toda la periferia.\n\n"
            "La versión Curvo del Arco Romano Mediano tiene un diseño más fluido y natural "
            "que la versión Recto, ideal para jardines paisajísticos y entornos naturales. "
            "Mismas dimensiones y capacidad que el modelo Recto pero con un estilo visual "
            "más contemporáneo.\n\n"
            "Fabricada en fibra de vidrio de primera calidad en Zárate, Buenos Aires. "
            "Instalación incluida. Consultar zona y flete antes de ofertar."
        ),
    },

    # ─── ARCO ROMANO GRANDE ────────────────────────────────────────────────────
    "Arco Romano Grande": {
        "titulo_ml": "Piscina arco romano grande 8x3.35 metros fibra de vidrio",
        "atributos_ml": {"BRAND": "EcoFiver", "MATERIAL": "Fibra de vidrio",
                         "LENGTH": "810", "WIDTH": "335", "DEPTH": "125", "CAPACITY": "41373"},
        "descripcion_ml": (
            "Piscina Arco Romano Grande de fibra de vidrio, 8,10 metros de largo por 3,35 "
            "metros de ancho. Profundidad variable de 1,25 a 1,80 metros. Capacidad de "
            "41.373 litros. La pileta más grande y completa de la línea Arco Romano: "
            "ideal como natatorio familiar o piscina semiprofesional.\n\n"
            "Con 8,10 metros de largo, esta pileta permite nadar a largo completo en crawl, "
            "espalda o pecho con espacio de sobra. La profundidad de 1,80 metros en la zona "
            "de nado permite saltos y zambullidas. La zona de playa de 1,25 metros es ideal "
            "para el descanso y el uso con niños.\n\n"
            "Casco de fibra de vidrio con laminado reforzado y gelcoat UV de alta durabilidad. "
            "Fabricado en Zárate, Buenos Aires, con 5 años de garantía en la estructura. "
            "Sin mantenimiento estructural ni pintura. Resistente a productos químicos de "
            "tratamiento y a las condiciones climáticas extremas de Argentina.\n\n"
            "Medidas: 8,10 m × 3,35 m, profundidad 1,25-1,80 m. La instalación incluye "
            "excavación, colocación, conexión hidráulica y puesta en marcha del sistema de "
            "filtrado. Consultar por flete e instalación según zona antes de ofertar. "
            "Financiación en cuotas."
        ),
    },

    "Arco Romano Grande Recto": {
        "titulo_ml": "Piscina arco romano grande 8x3.35 metros fibra de vidrio",
        "atributos_ml": {"BRAND": "EcoFiver", "MATERIAL": "Fibra de vidrio",
                         "LENGTH": "810", "WIDTH": "335", "DEPTH": "125", "CAPACITY": "41373"},
        "descripcion_ml": (
            "Pileta Arco Romano Grande Recto de fibra de vidrio, 8,10 metros de largo por "
            "3,35 metros de ancho. Profundidad variable de 1,25 a 1,80 metros. Capacidad de "
            "41.373 litros. Natatorio familiar de grandes dimensiones con la elegancia del "
            "diseño arco romano clásico en versión recta.\n\n"
            "El perfil recto en laterales y la curvatura solo en los extremos dan un aspecto "
            "formal y simétrico, ideal para jardines de diseño geométrico. La diferencia de "
            "profundidad crea zonas diferenciadas para adultos y niños.\n\n"
            "Fabricada en fibra de vidrio de alta resistencia en Zárate, Buenos Aires. "
            "Garantía de fábrica 5 años en estructura. Instalación incluida. Consultar zona "
            "de cobertura y flete antes de ofertar."
        ),
    },

    "Arco Romano Grande Curvo": {
        "titulo_ml": "Piscina arco romano curvo 8x3.35 metros fibra de vidrio",
        "atributos_ml": {"BRAND": "EcoFiver", "MATERIAL": "Fibra de vidrio",
                         "LENGTH": "810", "WIDTH": "335", "DEPTH": "125", "CAPACITY": "41373"},
        "descripcion_ml": (
            "Pileta Arco Romano Grande Curvo de fibra de vidrio, 8,10 metros de largo por "
            "3,35 metros de ancho. Profundidad variable de 1,25 a 1,80 metros. Capacidad de "
            "41.373 litros. Diseño con perfil completamente curvo en todo el perímetro para "
            "un aspecto natural y sofisticado.\n\n"
            "La versión Curvo del Arco Romano Grande es la elección ideal para jardines de "
            "diseño orgánico o paisajístico. Mismas dimensiones que la versión Recto, con un "
            "estilo visual más fluido. 8,10 metros de largo y 1,80 m de profundidad máxima "
            "para un natatorio familiar completo.\n\n"
            "Fabricada en fibra de vidrio en Zárate, Buenos Aires. Garantía 5 años en "
            "estructura. Instalación incluida en zona de cobertura. Consultar antes de ofertar."
        ),
    },

    # ─── PLAYA HÚMEDA ──────────────────────────────────────────────────────────
    "Playa Humeda": {
        "titulo_ml": "Piscina playa humeda fibra de vidrio 5.2x2.45 metros escalera",
        "atributos_ml": {"BRAND": "EcoFiver", "MATERIAL": "Fibra de vidrio",
                         "LENGTH": "520", "WIDTH": "245", "DEPTH": "110", "CAPACITY": "15288"},
        "descripcion_ml": (
            "Pileta Playa Húmeda de fibra de vidrio, 5,20 metros de largo por 2,45 metros de "
            "ancho. Profundidad variable de 1,10 a 1,30 metros. Capacidad de 15.288 litros. "
            "El modelo Playa Húmeda incorpora una zona de ingreso gradual en pendiente "
            "suave que simula la entrada al mar.\n\n"
            "La playa de ingreso gradual permite entrar al agua caminando sin necesidad de "
            "escalera, haciendo más cómodo y seguro el uso para niños, adultos mayores y "
            "personas con movilidad reducida. La zona de mayor profundidad (1,30 m) es "
            "adecuada para adultos y natación recreativa.\n\n"
            "Casco de fibra de vidrio fabricado en Zárate, Buenos Aires, con laminado de "
            "alta resistencia y gelcoat UV. Sin mantenimiento estructural, sin pintura. "
            "Superficie vitrificada interna: fácil limpieza y sin porosidades.\n\n"
            "Medidas: 5,20 m × 2,45 m, profundidad 1,10-1,30 m. Instalación incluida "
            "(excavación, nivelación, conexión hidráulica). Consultar zona de instalación "
            "y flete antes de ofertar. Financiación propia en cuotas."
        ),
    },

    "Playa Humeda Chica C/Escalera": {
        "titulo_ml": "Pileta playa humeda fibra de vidrio 4x2.4 metros con escalera",
        "atributos_ml": {"BRAND": "EcoFiver", "MATERIAL": "Fibra de vidrio",
                         "LENGTH": "410", "WIDTH": "240", "DEPTH": "120", "CAPACITY": "11808"},
        "descripcion_ml": (
            "Piscina Playa Húmeda Chica con Escalera de fibra de vidrio, 4,10 metros de largo "
            "por 2,40 metros de ancho y 1,20 metros de profundidad uniforme. Capacidad de "
            "11.808 litros. Combina la practicidad de la escalera de ingreso con la zona de "
            "playa húmeda en el extremo.\n\n"
            "El diseño incorpora escalera lateral para facilitar el ingreso y una plataforma "
            "de playa húmeda en el extremo opuesto, creando dos zonas de uso diferenciado. "
            "La profundidad de 1,20 m es adecuada para adultos y adolescentes.\n\n"
            "Fabricada en fibra de vidrio de alta resistencia en Zárate, Buenos Aires. "
            "No requiere pintura ni mantenimiento estructural. Instalación incluida "
            "(excavación, colocación, conexión hidráulica). Consultar zona y flete. "
            "Financiación en cuotas disponible."
        ),
    },

    "Semi Playa Humeda C/Escalera": {
        "titulo_ml": "Piscina semi playa humeda 6.7x2.95 metros fibra de vidrio",
        "atributos_ml": {"BRAND": "EcoFiver", "MATERIAL": "Fibra de vidrio",
                         "LENGTH": "670", "WIDTH": "295", "DEPTH": "150", "CAPACITY": "29663"},
        "descripcion_ml": (
            "Pileta Semi Playa Húmeda con Escalera de fibra de vidrio, 6,70 metros de largo "
            "por 2,95 metros de ancho y 1,50 metros de profundidad. Capacidad de 29.663 litros. "
            "Modelo grande que combina zona de nado profunda con zona de playa parcial y "
            "escalera de ingreso lateral.\n\n"
            "Con 6,70 metros de largo y 1,50 de profundidad, esta piscina está diseñada para "
            "el uso familiar intensivo. La zona de semi-playa en uno de los extremos crea "
            "un área más baja y confortable para niños y recreación, mientras el resto de "
            "la pileta tiene la profundidad ideal para el nado.\n\n"
            "Casco de fibra de vidrio de laminado reforzado, fabricado en Zárate, Buenos Aires. "
            "Garantía 5 años en estructura. Sin pintura ni mantenimiento estructural. "
            "Instalación completa incluida. Consultar zona y flete antes de ofertar."
        ),
    },

    # ─── PLAYA Y ABANICO ───────────────────────────────────────────────────────
    "Playa y Abanico": {
        "titulo_ml": "Piscina playa abanico fibra de vidrio 9.2x3.8 metros doble zona",
        "atributos_ml": {"BRAND": "EcoFiver", "MATERIAL": "Fibra de vidrio",
                         "LENGTH": "920", "WIDTH": "380", "DEPTH": "125", "CAPACITY": "53254"},
        "descripcion_ml": (
            "Piscina Playa y Abanico de fibra de vidrio, 9,20 metros de largo por 3,80 metros "
            "de ancho. Profundidad variable de 1,25 a 1,80 metros. Capacidad de 53.254 litros. "
            "La pileta más grande del catálogo EcoFiver: combina una zona de playa de ingreso "
            "gradual con un abanico (zona semicircular) de mayor profundidad para el nado.\n\n"
            "El diseño Playa y Abanico crea tres zonas claramente definidas: la zona de playa "
            "húmeda con ingreso gradual, la zona central de transición y el abanico profundo "
            "de 1,80 metros para nado, saltos y buceo. Ideal para familias numerosas y "
            "propiedades grandes.\n\n"
            "Casco de fibra de vidrio fabricado con laminado de alta resistencia en Zárate, "
            "Buenos Aires. 5 años de garantía en estructura. Sin pintura, sin fisuras, sin "
            "mantenimiento estructural. Resistencia UV y a los productos de tratamiento.\n\n"
            "Medidas: 9,20 m × 3,80 m, profundidad 1,25-1,80 m. Instalación incluida: "
            "excavación, colocación, conexión hidráulica completa y puesta en marcha del "
            "filtro. Por las dimensiones, consultar zona de instalación y logística antes "
            "de ofertar. Financiación propia en cuotas."
        ),
    },

    "Playa y Abanico Chica": {
        "titulo_ml": "Piscina playa abanico fibra de vidrio 9.2x3.8 metros doble zona",
        "atributos_ml": {"BRAND": "EcoFiver", "MATERIAL": "Fibra de vidrio",
                         "LENGTH": "920", "WIDTH": "380", "DEPTH": "125", "CAPACITY": "53254"},
        "descripcion_ml": (
            "Pileta Playa y Abanico Chica de fibra de vidrio, 9,20 metros de largo por 3,80 "
            "metros de ancho. Profundidad de 1,25 a 1,80 metros. Capacidad de 53.254 litros. "
            "Diseño con zona de playa de ingreso gradual y abanico profundo para el nado.\n\n"
            "La combinación de playa y abanico permite el uso simultáneo de toda la familia: "
            "zona baja segura para niños y zona profunda para adultos. El formato semicircular "
            "del abanico optimiza el espacio disponible.\n\n"
            "Fabricada en fibra de vidrio en Zárate, Buenos Aires. Garantía 5 años. "
            "Instalación incluida. Consultar zona y flete antes de ofertar."
        ),
    },

    "Playa y Abanico Mediana": {
        "titulo_ml": "Piscina playa abanico fibra de vidrio 9.2x3.8 metros con playa",
        "atributos_ml": {"BRAND": "EcoFiver", "MATERIAL": "Fibra de vidrio",
                         "LENGTH": "920", "WIDTH": "380", "DEPTH": "125", "CAPACITY": "53254"},
        "descripcion_ml": (
            "Piscina Playa y Abanico Mediana de fibra de vidrio, 9,20 metros de largo por "
            "3,80 metros de ancho. Profundidad 1,25 a 1,80 metros. Capacidad de 53.254 litros. "
            "Diseño con playa de ingreso gradual y zona de abanico profundo.\n\n"
            "Natatorio familiar de grandes dimensiones con doble zona de uso: playa baja "
            "para niños y recreación, abanico profundo para nado y saltos. Fabricada en "
            "fibra de vidrio de primera calidad en Zárate, Buenos Aires.\n\n"
            "Garantía 5 años en estructura. Instalación incluida. Consultar zona y flete."
        ),
    },

    "Playa y Abanico Grande": {
        "titulo_ml": "Piscina playa y abanico grande fibra de vidrio 9.2x3.8 metros",
        "atributos_ml": {"BRAND": "EcoFiver", "MATERIAL": "Fibra de vidrio",
                         "LENGTH": "920", "WIDTH": "380", "DEPTH": "125", "CAPACITY": "53254"},
        "descripcion_ml": (
            "Pileta Playa y Abanico Grande de fibra de vidrio, 9,20 metros de largo por 3,80 "
            "metros de ancho. Profundidad de 1,25 a 1,80 metros. Capacidad de 53.254 litros. "
            "El modelo más amplio de la línea Playa y Abanico para propiedades y familias "
            "que buscan la experiencia máxima en el hogar.\n\n"
            "Playa de ingreso gradual + abanico profundo de 1,80 metros = la piscina ideal "
            "para uso intensivo familiar. 9,20 metros de largo garantizan espacio para nadar "
            "y disfrutar sin aglomeraciones.\n\n"
            "Fabricada en fibra de vidrio en Zárate, Buenos Aires. Garantía 5 años. "
            "Instalación incluida. Consultar disponibilidad logística antes de ofertar."
        ),
    },

    # ─── MINIMALISTA ───────────────────────────────────────────────────────────
    "Minimalista Chica": {
        "titulo_ml": "Pileta minimalista rectangular fibra de vidrio 4x2.5 metros",
        "atributos_ml": {"BRAND": "EcoFiver", "MATERIAL": "Fibra de vidrio",
                         "LENGTH": "397", "WIDTH": "246", "DEPTH": "120", "CAPACITY": "11712"},
        "descripcion_ml": (
            "Piscina Minimalista Chica de fibra de vidrio, 3,97 metros de largo por 2,46 "
            "metros de ancho y 1,20 metros de profundidad uniforme. Capacidad de 11.712 litros. "
            "Diseño rectangular con líneas rectas y limpias, pensado para jardines modernos "
            "y espacios contemporáneos.\n\n"
            "El estilo Minimalista se define por sus bordes rectos en los cuatro lados, sin "
            "curvas ni ornamentos. Es la pileta preferida para proyectos de arquitectura y "
            "paisajismo moderno, integra perfectamente con decks de madera, hormigón y "
            "jardines de diseño geométrico.\n\n"
            "Casco de fibra de vidrio fabricado en Zárate, Buenos Aires, con gelcoat disponible "
            "en varios colores (consultar disponibilidad). 1,20 metros de profundidad, ideal "
            "para adultos y natación recreativa. Sin mantenimiento estructural ni pintura.\n\n"
            "Medidas: 3,97 m × 2,46 m × 1,20 m de profundidad. Instalación incluida "
            "(excavación, colocación, conexión hidráulica). Consultar zona de instalación "
            "y flete antes de ofertar. Financiación en cuotas."
        ),
    },

    "Minimalista Mediana": {
        "titulo_ml": "Piscina minimalista rectangular 5.5x2.9 metros fibra de vidrio",
        "atributos_ml": {"BRAND": "EcoFiver", "MATERIAL": "Fibra de vidrio",
                         "LENGTH": "550", "WIDTH": "290", "DEPTH": "150", "CAPACITY": "23925"},
        "descripcion_ml": (
            "Pileta Minimalista Mediana de fibra de vidrio, 5,50 metros de largo por 2,90 "
            "metros de ancho y 1,50 metros de profundidad uniforme. Capacidad de 23.925 litros. "
            "El modelo más elegido de la línea Minimalista: largo de nado real, profundidad "
            "adulta y diseño contemporáneo de líneas rectas.\n\n"
            "Con 5,50 metros de largo y 1,50 de profundidad, esta piscina permite nadar a "
            "largo completo con comodidad. Las líneas rectas en los cuatro lados la hacen "
            "ideal para jardines de diseño moderno, integración con decks, pérgolas y "
            "espacios de arquitectura contemporánea.\n\n"
            "Fabricada en fibra de vidrio de alta resistencia en Zárate, Buenos Aires. "
            "No requiere pintura ni mantenimiento estructural. Garantía de fábrica 5 años. "
            "La instalación incluye excavación, colocación, conexión hidráulica y puesta "
            "en marcha del sistema de filtrado.\n\n"
            "Medidas: 5,50 m × 2,90 m × 1,50 m de profundidad. Consultar zona de "
            "instalación y flete antes de ofertar. Financiación en cuotas disponible."
        ),
    },

    "Minimalista Grande": {
        "titulo_ml": "Piscina minimalista rectangular 6.4x3 metros fibra de vidrio",
        "atributos_ml": {"BRAND": "EcoFiver", "MATERIAL": "Fibra de vidrio",
                         "LENGTH": "640", "WIDTH": "300", "DEPTH": "140", "CAPACITY": "26880"},
        "descripcion_ml": (
            "Pileta Minimalista Grande de fibra de vidrio, 6,40 metros de largo por 3,00 "
            "metros de ancho y 1,40 metros de profundidad uniforme. Capacidad de 26.880 litros. "
            "El modelo más grande de la línea Minimalista: máxima superficie de nado, diseño "
            "de líneas rectas y profundidad ideal para adultos.\n\n"
            "6,40 metros de largo y 3 metros de ancho definen un natatorio familiar de primer "
            "nivel. La profundidad de 1,40 metros es la estándar para piscinas de uso deportivo "
            "y recreativo. Las líneas completamente rectas en los cuatro lados la hacen el "
            "modelo favorito para arquitectos y paisajistas modernos.\n\n"
            "Casco de fibra de vidrio con laminado reforzado, gelcoat UV de alta durabilidad, "
            "fabricado en Zárate, Buenos Aires. Sin pintura, sin fisuras, sin mantenimiento "
            "estructural. 5 años de garantía en estructura.\n\n"
            "Medidas: 6,40 m × 3,00 m × 1,40 m de profundidad. Instalación incluida: "
            "excavación, nivelación, colocación, conexión hidráulica completa. "
            "Consultar zona de instalación y flete antes de ofertar. Financiación en cuotas."
        ),
    },

    # ─── RECTA CON ESCALERA ────────────────────────────────────────────────────
    "Recta C/Mini Escalera": {
        "titulo_ml": "Pileta rectangular fibra de vidrio 4.6x2.5 metros con escalera",
        "atributos_ml": {"BRAND": "EcoFiver", "MATERIAL": "Fibra de vidrio",
                         "LENGTH": "463", "WIDTH": "248", "DEPTH": "125", "CAPACITY": "14353"},
        "descripcion_ml": (
            "Piscina Recta con Mini Escalera de fibra de vidrio, 4,63 metros de largo por "
            "2,48 metros de ancho y 1,25 metros de profundidad uniforme. Capacidad de "
            "14.353 litros. Modelo rectangular con escalera integrada para un ingreso "
            "cómodo y seguro desde dentro de la pileta.\n\n"
            "La mini escalera integrada en el casco es una característica que diferencia "
            "este modelo: el ingreso se hace desde dentro de la pileta sin necesidad de "
            "escalerita externa de acero inoxidable. Esto mejora la estética y evita "
            "el mantenimiento de partes metálicas.\n\n"
            "Forma rectangular con líneas rectas, 4,63 metros de largo y 1,25 de profundidad, "
            "ideal para nado recreativo y uso familiar. Fabricada en fibra de vidrio de alta "
            "resistencia en Zárate, Buenos Aires. Sin pintura ni mantenimiento estructural.\n\n"
            "Medidas: 4,63 m × 2,48 m × 1,25 m de profundidad. Instalación incluida "
            "(excavación, colocación, conexión hidráulica). Consultar zona y flete. "
            "Financiación en cuotas disponible."
        ),
    },
}


# ─── MÓDULOS HABITACIONALES ────────────────────────────────────────────────────

def ficha_modulo(m2: int) -> dict:
    """Genera la ficha de producto para un módulo habitacional según su superficie."""
    dormitorios = {6: "estudio", 12: "1 dormitorio", 18: "2 dormitorios",
                   24: "2-3 dormitorios", 30: "3 dormitorios"}.get(m2, f"{m2//12} dormitorios")
    titulo = f"Casa prefabricada {m2}m2 wood frame llave en mano {dormitorios}"[:60]
    descripcion = (
        f"Módulo habitacional de {m2} m² de superficie, sistema constructivo Wood Frame. "
        f"Estructura de madera de pino tratado, revestimiento exterior en placas cementicias "
        f"y terminación interior en Durlock. Entrega llave en mano con todas las terminaciones "
        f"incluidas.\n\n"
        f"El sistema Wood Frame es el estándar en construcción modular de Estados Unidos, "
        f"Canadá y Europa. Ofrece excelente aislación térmica y acústica, resistencia "
        f"sísmica superior a la mampostería tradicional, y tiempos de obra significativamente "
        f"menores a la construcción convencional.\n\n"
        f"Con {m2} m² de superficie, el módulo puede configurarse como {dormitorios}, "
        f"oficina, local comercial, ampliación de vivienda existente o espacio de trabajo. "
        f"La planta se puede adaptar a las necesidades del cliente.\n\n"
        f"Incluye: estructura Wood Frame completa, aislación térmica, revestimiento exterior, "
        f"terminación interior en Durlock, puertas, ventanas, instalación eléctrica interna "
        f"y pintura completa. No incluye: fundación, conexión a servicios externos, piso.\n\n"
        f"Fabricado en Zárate, Buenos Aires. Instalación a cargo de nuestro equipo. "
        f"Consultar zona de cobertura y logística antes de ofertar. "
        f"Financiación propia en cuotas disponible."
    )
    return {"titulo_ml": titulo, "descripcion_ml": descripcion}


# Fichas estáticas de módulos estándar
FICHAS_MODULOS: dict = {
    str(m2): ficha_modulo(m2)
    for m2 in [6, 12, 18, 24, 30, 36, 42, 48, 54, 60]
}


# ─── HIDROMASAJES / SPAS ──────────────────────────────────────────────────────

FICHAS_HIDROMASAJES: dict = {

    "Spa Quadra": {
        "titulo_ml": "Hidromasaje esquinero acrílico 1.10x1.10 4 jets con estructura",
        "atributos_ml": {"BRAND": "EcoFiver", "MATERIAL": "Acrílico sanitario",
                         "LENGTH": "110", "WIDTH": "110", "DEPTH": "10"},
        "descripcion_ml": (
            "Hidromasaje Spa Quadra de acrílico sanitario reforzado con PRFV, formato esquinero "
            "ultracompacto de 1,10 m × 1,10 m. Ideal para baños pequeños y espacios reducidos "
            "donde el hidromasaje convencional no entra.\n\n"
            "El Spa Quadra incluye 4 jets dirigibles con vista cromo, motor de 1/2 o 3/4 HP, "
            "1 pulsador neumático de encendido, 1 regulador de flujo de aire, sistema de succión "
            "completo (filtro de pelos + sopapa + desborde conectados) y estructura autoportante "
            "metálica reforzada. Todo incluido en el precio.\n\n"
            "El acrílico sanitario de alta resistencia reforzado con PRFV (Poliéster Reforzado en "
            "Fibra de Vidrio) es el material premium para hidromasajes: superficie no porosa, fácil "
            "limpieza, resistente al calor y a los productos de tratamiento. No se fisura ni opaca "
            "con el uso.\n\n"
            "Disponible en colores Blanco, Beige, Negro y Gris sin cargo adicional. "
            "Instalación sin obra de albañilería: conexión a agua fría/caliente existente, "
            "desagüe y electricidad. Sin financiación propia en cuotas — pago contado, "
            "tarjeta de crédito o débito. Entrega desde San Telmo (CABA) o Zárate (Buenos Aires). "
            "Cotizar envío a domicilio según zona. Garantía estructural incluida."
        ),
    },

    "Spa Recta": {
        "titulo_ml": "Hidromasaje rectangular acrílico 1.65x1.40 6 jets para dos personas",
        "atributos_ml": {"BRAND": "EcoFiver", "MATERIAL": "Acrílico sanitario",
                         "LENGTH": "165", "WIDTH": "140", "DEPTH": "45"},
        "descripcion_ml": (
            "Hidromasaje Spa Recta de acrílico sanitario reforzado con PRFV, diseño rectangular "
            "de 1,65 m de largo × 1,40 m de ancho. Formato confort para dos personas con "
            "profundidad de 0,45 m.\n\n"
            "El Spa Recta incluye 6 jets dirigibles con vista cromo, motor de 3/4 HP, "
            "1 pulsador neumático de encendido, 2 reguladores de flujo de aire, sistema de succión "
            "completo (filtro de pelos + sopapa + desborde conectados) y estructura autoportante "
            "metálica reforzada. Todo incluido.\n\n"
            "El diseño rectangular permite aprovechar el espacio de baño de forma eficiente. "
            "Con 6 jets y motor de 3/4 HP, el Spa Recta ofrece una hidroterapia de nivel "
            "superior: jets masajeadores dirigibles para espalda, lumbar y piernas.\n\n"
            "El acrílico sanitario reforzado con PRFV es duradero, de fácil limpieza y "
            "resistente al calor y productos de spa. Sin mantenimiento estructural. "
            "Disponible en Blanco, Beige, Negro y Gris sin cargo adicional. "
            "Instalación sin obra: conexión a agua caliente/fría, desagüe y eléctrico. "
            "Pago contado o tarjeta. Entrega desde San Telmo o Zárate. Consultar flete."
        ),
    },

    "Spa Orbis": {
        "titulo_ml": "Hidromasaje circular acrílico 1.76 diámetro 6 jets spa de lujo",
        "atributos_ml": {"BRAND": "EcoFiver", "MATERIAL": "Acrílico sanitario",
                         "LENGTH": "176", "WIDTH": "176", "DEPTH": "40"},
        "descripcion_ml": (
            "Hidromasaje Spa Orbis de acrílico sanitario reforzado con PRFV, formato circular "
            "panorámico de 1,76 m de diámetro. Diseño premium para baños de lujo, terrazas, "
            "jardines o ambientes SPA. Ideal como pieza central del baño principal.\n\n"
            "El Spa Orbis incluye 6 a 8 jets dirigibles con vista cromo, motor de 3/4 HP, "
            "1 pulsador neumático de encendido, 2 reguladores de flujo de aire, sistema de succión "
            "completo y estructura autoportante metálica reforzada. Todo incluido en el precio.\n\n"
            "El formato circular ofrece una distribución de jets de 360 grados, masajeando "
            "uniformemente todo el cuerpo. Profundidad de 0,40 m, adecuada para uso en "
            "posición reclinada. El diseño redondo se adapta a espacios libres de ángulos "
            "y da un aspecto spa de alta gama.\n\n"
            "Material: acrílico sanitario de alta resistencia reforzado con PRFV — no poroso, "
            "resistente al calor, al cloro y a otros productos de tratamiento. "
            "Disponible en Blanco, Beige, Negro y Gris. Instalación sin obra de albañilería. "
            "Pago contado o tarjeta. Entrega desde San Telmo (CABA) o Zárate (Buenos Aires)."
        ),
    },

    "Spa Delta": {
        "titulo_ml": "Hidromasaje mini spa acrílico 1.97x1.42 8 jets motor 1HP",
        "atributos_ml": {"BRAND": "EcoFiver", "MATERIAL": "Acrílico sanitario",
                         "LENGTH": "197", "WIDTH": "142", "DEPTH": "52"},
        "descripcion_ml": (
            "Hidromasaje Spa Delta de acrílico sanitario reforzado con PRFV, el modelo más grande "
            "de la línea: 1,97 m de largo × 1,42 m de ancho y 0,52 m de profundidad. "
            "Categoría mini spa rectangular XL para uso familiar o profesional.\n\n"
            "El Spa Delta incluye 8 jets dirigibles con vista cromo, motor de 1 HP (el más "
            "potente de la línea), 1 pulsador neumático de encendido, 2 reguladores de flujo "
            "de aire, sistema de succión completo (filtro de pelos + sopapa + desborde "
            "conectados) y estructura autoportante metálica reforzada.\n\n"
            "Con 8 jets y motor de 1 HP, el Spa Delta es el hidromasaje con mayor potencia "
            "de hidroterapia de la línea EcoFiver. La profundidad de 0,52 m permite sumergirse "
            "completamente y aprovechar todos los puntos de masaje. Ideal para uso diario, "
            "recuperación muscular y relajación profunda.\n\n"
            "Material: acrílico sanitario de alta resistencia reforzado con PRFV — no poroso, "
            "resistente al calor y a los productos de spa. Disponible en Blanco, Beige, Negro "
            "y Gris sin cargo adicional. Instalación sin obra. Pago contado o tarjeta. "
            "Entrega desde San Telmo (CABA) o Zárate (Buenos Aires). Garantía estructural."
        ),
    },
}


# ─── BAÑERAS DE ACRÍLICO ──────────────────────────────────────────────────────

FICHAS_BANERAS: dict = {

    "Lumina": {
        "titulo_ml": "Bañera rectangular acrílico 1.90x0.90 metros sanitaria",
        "atributos_ml": {"BRAND": "EcoFiver", "MATERIAL": "Acrílico sanitario",
                         "LENGTH": "190", "WIDTH": "90", "DEPTH": "50"},
        "descripcion_ml": (
            "Bañera Lumina de acrílico sanitario reforzado con PRFV, formato rectangular de "
            "1,90 m de largo × 0,90 m de ancho. Ideal para baños amplios. "
            "Profundidad de 0,50 m para una inmersión cómoda.\n\n"
            "La bañera Lumina es el modelo estándar de mayor tamaño de la línea EcoFiver. "
            "Su formato rectangular clásico se adapta a la mayoría de los baños principales. "
            "El acrílico sanitario de alta resistencia reforzado con PRFV ofrece una superficie "
            "tersa, no porosa, fácil de limpiar y resistente al calor del agua.\n\n"
            "Instalación directa sobre el piso existente. Conexión a agua fría/caliente y "
            "desagüe estándar. Sin obra de albañilería. No requiere estructura especial. "
            "Disponible en colores Blanco, Beige, Negro y Gris sin cargo adicional. "
            "Pago contado o tarjeta de crédito/débito. Sin financiación propia en cuotas. "
            "Entrega desde San Telmo (CABA) o Zárate (Buenos Aires). Cotizar envío según zona. "
            "Garantía estructural incluida."
        ),
    },

    "Sensa": {
        "titulo_ml": "Bañera angular doble asiento acrílico 1.70x1.18 para dos personas",
        "atributos_ml": {"BRAND": "EcoFiver", "MATERIAL": "Acrílico sanitario",
                         "LENGTH": "170", "WIDTH": "118", "DEPTH": "45"},
        "descripcion_ml": (
            "Bañera Sensa de acrílico sanitario reforzado con PRFV, formato angular doble "
            "de 1,70 m × 1,18 m. Diseñada para dos personas con dos asientos moldeados "
            "enfrentados. Profundidad de 0,45 m.\n\n"
            "El formato angular de la bañera Sensa aprovecha el espacio del baño de manera "
            "eficiente y permite una experiencia de baño compartida con posición ergonómica "
            "para cada usuario. Los dos asientos moldeados brindan soporte lumbar y cervical "
            "durante la inmersión.\n\n"
            "El acrílico sanitario PRFV es el material premium para bañeras: superficie lisa, "
            "no porosa, resistente al calor (hasta 70°C del agua), fácil de limpiar y "
            "duradera sin pintura ni mantenimiento. "
            "Disponible en Blanco, Beige, Negro y Gris. Instalación directa, sin obra. "
            "Pago contado o tarjeta. Entrega desde San Telmo o Zárate. Consultar flete."
        ),
    },

    "Vento": {
        "titulo_ml": "Bañera compacta acrílico 1.40x0.77 metros baños chicos",
        "atributos_ml": {"BRAND": "EcoFiver", "MATERIAL": "Acrílico sanitario",
                         "LENGTH": "140", "WIDTH": "77", "DEPTH": "49"},
        "descripcion_ml": (
            "Bañera Vento de acrílico sanitario reforzado con PRFV, formato compacto de "
            "1,40 m de largo × 0,77 m de ancho. La opción ideal cuando el baño tiene espacio "
            "reducido pero se quiere incorporar una bañera. Profundidad de 0,49 m.\n\n"
            "La bañera Vento es la más compacta de la línea EcoFiver, especialmente diseñada "
            "para baños pequeños de departamentos o casas donde el espacio disponible no permite "
            "una bañera de tamaño estándar. Sin sacrificar comodidad ni calidad de material.\n\n"
            "Acrílico sanitario de alta resistencia reforzado con PRFV: superficie no porosa, "
            "tersa, fácil de limpiar y resistente al calor del agua. Sin mantenimiento especial. "
            "Disponible en Blanco, Beige, Negro y Gris sin cargo adicional. "
            "Instalación directa sobre el piso. Conexión a agua y desagüe estándar, sin obra. "
            "Pago contado o tarjeta. Garantía estructural incluida. "
            "Entrega desde San Telmo (CABA) o Zárate (Buenos Aires)."
        ),
    },

    "Aqua": {
        "titulo_ml": "Bañera doble asiento XL acrílico 1.65x1.40 baños de lujo",
        "atributos_ml": {"BRAND": "EcoFiver", "MATERIAL": "Acrílico sanitario",
                         "LENGTH": "165", "WIDTH": "140", "DEPTH": "50"},
        "descripcion_ml": (
            "Bañera Aqua de acrílico sanitario reforzado con PRFV, formato doble asiento XL "
            "de 1,65 m × 1,40 m y 0,50 m de profundidad. El modelo de mayor capacidad de la "
            "línea, pensado para baños de lujo, suites y ambientes premium.\n\n"
            "La bañera Aqua ofrece dos asientos enfrentados con amplio espacio interior, "
            "ideal para parejas o para quien busca la máxima comodidad en el baño. "
            "El formato cuadrado-amplio permite sumergirse completamente con espacio para "
            "estirar las piernas en ambas posiciones.\n\n"
            "Fabricada en acrílico sanitario de alta resistencia reforzado con PRFV — "
            "el mismo material usado en bañeras de spa de alto nivel. Superficie no porosa, "
            "tersa, de fácil limpieza y duradera. No requiere pintura ni mantenimiento especial. "
            "Disponible en Blanco, Beige, Negro y Gris. Instalación directa sin obra. "
            "Pago contado o tarjeta. Entrega desde San Telmo o Zárate. "
            "Consultar envío a domicilio según zona. Garantía estructural incluida."
        ),
    },

    "Curve": {
        "titulo_ml": "Bañera esquinera cuadrada acrílico 1.40x1.40 metros aprovecha rincón",
        "atributos_ml": {"BRAND": "EcoFiver", "MATERIAL": "Acrílico sanitario",
                         "LENGTH": "140", "WIDTH": "140", "DEPTH": "55"},
        "descripcion_ml": (
            "Bañera Curve de acrílico sanitario reforzado con PRFV, formato esquinero cuadrado "
            "de 1,40 m × 1,40 m. Diseñada para instalarse en el rincón del baño, aprovechando "
            "el espacio de esquina que normalmente queda sin uso. Profundidad de 0,55 m — "
            "la mayor de la línea.\n\n"
            "La bañera Curve tiene la mayor profundidad de toda la línea EcoFiver (0,55 m), "
            "lo que permite una inmersión total con el agua hasta el hombro. El formato "
            "esquinero cuadrado crea un ambiente de spa doméstico en el rincón del baño, "
            "maximizando el espacio disponible.\n\n"
            "Material: acrílico sanitario de alta resistencia reforzado con PRFV — no poroso, "
            "resistente al calor, fácil de limpiar y duradero. Sin mantenimiento especial. "
            "Disponible en Blanco, Beige, Negro y Gris sin cargo adicional. "
            "Instalación directa sobre el piso, sin obra. Conexión estándar a agua y desagüe. "
            "Pago contado o tarjeta. Entrega desde San Telmo (CABA) o Zárate (Buenos Aires)."
        ),
    },

    "Pure": {
        "titulo_ml": "Bañera rectangular clásica acrílico 1.84x0.96 alta profundidad",
        "atributos_ml": {"BRAND": "EcoFiver", "MATERIAL": "Acrílico sanitario",
                         "LENGTH": "184", "WIDTH": "96", "DEPTH": "45"},
        "descripcion_ml": (
            "Bañera Pure de acrílico sanitario reforzado con PRFV, formato rectangular clásico "
            "de 1,84 m de largo × 0,96 m de ancho. El modelo con el ancho más generoso de la "
            "línea rectangular, con profundidad de 0,45 m.\n\n"
            "La bañera Pure combina el formato clásico con dimensiones interiores amplias: "
            "casi 2 metros de largo y casi 1 metro de ancho ofrecen el mayor espacio interior "
            "de los modelos rectangulares EcoFiver. Ideal para quien busca una bañera "
            "tradicional con el máximo confort.\n\n"
            "Fabricada en acrílico sanitario de alta resistencia reforzado con PRFV — "
            "superficie no porosa, resistente al calor del agua, de fácil limpieza y "
            "duradera. Sin pintura ni mantenimiento estructural especial. "
            "Disponible en Blanco, Beige, Negro y Gris. Instalación directa sin obra. "
            "Pago contado o tarjeta de crédito/débito. Sin financiación propia en cuotas. "
            "Entrega desde San Telmo (CABA) o Zárate (Buenos Aires). Consultar flete."
        ),
    },

    "Vita": {
        "titulo_ml": "Bañera rectangular estándar acrílico 1.80x0.90 metros versátil",
        "atributos_ml": {"BRAND": "EcoFiver", "MATERIAL": "Acrílico sanitario",
                         "LENGTH": "180", "WIDTH": "90", "DEPTH": "50"},
        "descripcion_ml": (
            "Bañera Vita de acrílico sanitario reforzado con PRFV, formato rectangular estándar "
            "de 1,80 m de largo × 0,90 m de ancho. La bañera más versátil de la línea: "
            "dimensiones universales que se adaptan a la gran mayoría de los baños. "
            "Profundidad de 0,50 m.\n\n"
            "La bañera Vita es el equilibrio perfecto entre tamaño y comodidad. Con 1,80 m × "
            "0,90 m y 0,50 m de profundidad, se ajusta a los baños estándar argentinos sin "
            "necesidad de reformas. Líneas rectas y perfil moderno.\n\n"
            "Material: acrílico sanitario de alta resistencia reforzado con PRFV — superficie "
            "no porosa, tersa, resistente al calor del agua (hasta 70°C) y a los productos "
            "de limpieza. Sin mantenimiento especial. "
            "Disponible en Blanco, Beige, Negro y Gris sin cargo adicional. "
            "Instalación directa sobre el piso. Sin obra de albañilería. "
            "Conexión estándar a agua fría/caliente y desagüe. "
            "Pago contado o tarjeta. Entrega desde San Telmo o Zárate. "
            "Garantía estructural incluida."
        ),
    },
}


# ─── RECEPTÁCULOS DE DUCHA ────────────────────────────────────────────────────

FICHAS_RECEPTACULOS: dict = {

    "Clásico": {
        "titulo_ml": "Receptáculo ducha acrílico 1.10x1.10 cuadrado antideslizante",
        "atributos_ml": {"BRAND": "EcoFiver", "MATERIAL": "Acrílico sanitario",
                         "LENGTH": "110", "WIDTH": "110", "DEPTH": "10"},
        "descripcion_ml": (
            "Receptáculo de ducha Clásico de acrílico sanitario reforzado con PRFV, "
            "formato cuadrado de 1,10 m × 1,10 m. El modelo más popular de la línea "
            "EcoFiver para duchas. Profundidad de 0,10 m con superficie antideslizante.\n\n"
            "El receptáculo Clásico es la base de ducha estándar por excelencia: medidas "
            "universales que se adaptan a la mayoría de los boxes de ducha. "
            "La superficie antideslizante integrada en el acrílico brinda seguridad en el uso "
            "diario, especialmente en hogares con niños y adultos mayores.\n\n"
            "El acrílico sanitario de alta resistencia reforzado con PRFV ofrece una superficie "
            "no porosa, fácil de limpiar y resistente a jabones, champús y productos de "
            "limpieza habituales. Sin manchas ni calcificación visible. "
            "Instalación directa sobre el piso. Conexión a desagüe estándar. Sin obra. "
            "Disponible en Blanco, Beige, Negro y Gris sin cargo adicional. "
            "Pago contado o tarjeta. Entrega desde San Telmo (CABA) o Zárate (Buenos Aires)."
        ),
    },

    "Esquinero": {
        "titulo_ml": "Receptáculo ducha esquinero acrílico 99x75 cm antideslizante",
        "atributos_ml": {"BRAND": "EcoFiver", "MATERIAL": "Acrílico sanitario",
                         "LENGTH": "99", "WIDTH": "75", "DEPTH": "10"},
        "descripcion_ml": (
            "Receptáculo de ducha Esquinero de acrílico sanitario reforzado con PRFV, "
            "99 cm de largo × 75 cm de ancho. Diseñado para aprovechar los rincones del baño "
            "con el menor espacio posible. Profundidad de 0,10 m con superficie antideslizante.\n\n"
            "El receptáculo Esquinero es la solución para baños pequeños donde el espacio "
            "es limitado pero se quiere instalar una ducha cómoda. El formato rectangular "
            "asimétrico se adapta perfectamente al rincón del baño, dejando libre el resto "
            "del espacio disponible.\n\n"
            "Fabricado en acrílico sanitario de alta resistencia reforzado con PRFV — "
            "superficie antideslizante integrada, no porosa, fácil de limpiar y resistente "
            "a los productos de higiene habituales. Sin calcificación visible. "
            "Instalación directa, sin obra. Conexión a desagüe estándar. "
            "Disponible en Blanco, Beige, Negro y Gris. Pago contado o tarjeta. "
            "Entrega desde San Telmo (CABA) o Zárate (Buenos Aires). Consultar flete."
        ),
    },

    "Pequeño": {
        "titulo_ml": "Receptáculo ducha cuadrado acrílico 90x90 cm compacto antideslizante",
        "atributos_ml": {"BRAND": "EcoFiver", "MATERIAL": "Acrílico sanitario",
                         "LENGTH": "90", "WIDTH": "90", "DEPTH": "9"},
        "descripcion_ml": (
            "Receptáculo de ducha Pequeño de acrílico sanitario reforzado con PRFV, "
            "formato cuadrado compacto de 90 cm × 90 cm. La base de ducha más pequeña "
            "de la línea EcoFiver, para baños con espacio muy reducido. "
            "Profundidad de 0,09 m con superficie antideslizante.\n\n"
            "El receptáculo Pequeño es ideal para baños de servicio, toilettes ampliados, "
            "departamentos pequeños o cualquier espacio donde el ancho mínimo lo exige. "
            "A pesar de sus dimensiones compactas, mantiene la calidad de material de toda "
            "la línea EcoFiver.\n\n"
            "Acrílico sanitario de alta resistencia reforzado con PRFV: superficie "
            "antideslizante integrada, no porosa, resistente a jabones y productos de "
            "limpieza. Fácil mantenimiento, sin calcificación visible. "
            "Instalación directa sobre el piso. Sin obra de albañilería. "
            "Conexión a desagüe estándar. Disponible en Blanco, Beige, Negro y Gris. "
            "Pago contado o tarjeta. Entrega desde San Telmo (CABA) o Zárate. Consultar flete."
        ),
    },
}
