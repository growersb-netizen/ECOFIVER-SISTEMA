"""
Catálogo oficial de productos EcoFiver.
Este archivo es importado por TODOS los agentes.
"""

CATALOGO = {
    "piscinas": [
        {"id": 1,  "modelo": "Minideck",                        "medida": "3,55x2,10 Deck / 3x2x70",     "precio": 2500000},
        {"id": 2,  "modelo": "Miniportante",                    "medida": "2,50x2,10x70",                 "precio": 2000000},
        {"id": 3,  "modelo": "Autoportante",                    "medida": "4,10x2,10x70",                 "precio": 2500000},
        {"id": 4,  "modelo": "Arco Romano Chico Recto",         "medida": "4,60x2,47x1,20",               "precio": 3900000},
        {"id": 5,  "modelo": "Arco Romano Chico C/Desnivel",    "medida": "4,60x2,35x1,10 a 1,30",        "precio": 2990000},
        {"id": 6,  "modelo": "Arco Romano Mediano Recto",       "medida": "6,40x2,94x1,40",               "precio": 3690000},
        {"id": 7,  "modelo": "Arco Romano Mediano C/Desnivel",  "medida": "7x3,35x1,25 a 1,70",           "precio": 4900000},
        {"id": 8,  "modelo": "Arco Romano Grande",              "medida": "8,10x3,35x1,25 a 1,80",        "precio": 5200000},
        {"id": 9,  "modelo": "Playa Humeda",                    "medida": "5,20x2,45x1,10 a 1,30",        "precio": 3290000},
        {"id": 10, "modelo": "Minimalista Chica",               "medida": "3,97x2,46x1,20",               "precio": 3700000},
        {"id": 11, "modelo": "Minimalista Mediana",             "medida": "5,50x2,90x1,50",               "precio": 5900000},
        {"id": 12, "modelo": "Minimalista Grande",              "medida": "6,40x3x1,40",                  "precio": 6500000},
        {"id": 13, "modelo": "Recta C/Mini Escalera",           "medida": "4,63x2,48x1,25",               "precio": 4500000},
        {"id": 14, "modelo": "Playa Humeda Chica C/Escalera",   "medida": "4,10x2,40x1,20",               "precio": 3800000},
        {"id": 15, "modelo": "Semi Playa Humeda C/Escalera",    "medida": "6,70x2,95x1,50",               "precio": 4500000},
        {"id": 16, "modelo": "Playa y Abanico",                 "medida": "9,20x3,80x1,25 a 1,80",        "precio": 5500000},
    ],
    "modulos_m2": [6, 12, 18, 24, 30, 36, 42, 48, 54, 60, 66, 72],
    # Precios módulos CONTADO (precio fijo para 6/12/18; proporcional al 18m² para mayores)
    "modulos_precios_contado": {6: 2990000, 12: 4980000, 18: 7480000},
    "modulos_precio_m2_base": 7480000 / 18,   # ~415.556/m² para >18m²
    # Precio módulos FINANCIADO: $510.000/m² (cualquier superficie, múltiplos de 6)
    "modulos_precio_m2_financiado": 510000,
    "flete_por_km": 4000,
    "flete_miniportante_por_km": 4000,
    "flete_financiado": 0,       # BONIFICADO en financiación (piscinas, módulos, combos)
    "fabrica_direccion": "Av. Antártida Argentina 3105, Zárate, Buenos Aires",
    "ciudad_origen": "Zárate",
    "combo_descuento_pct": 25,
    "combo_solo_financiacion": True,
    "planes_financiacion": {
        "12":  {"cuotas": 12},
        "18":  {"cuotas": 18},
        "24":  {"cuotas": 24},
        "36":  {"cuotas": 36},
        "60":  {"cuotas": 60},
        "120": {"cuotas": 120},
    },
    # Ingreso = N cuotas del plan elegido (no porcentaje fijo)
    # Mismo factor para módulos y piscinas — regla real confirmada (antes
    # piscinas usaba 1.5, un bug que las prompts de los agentes ya daban
    # por corregido pero el simulador real seguía usando el valor viejo).
    "factor_ingreso_modulos":  2.0,
    "factor_ingreso_piscinas": 2.0,
}
