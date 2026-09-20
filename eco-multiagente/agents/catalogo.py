"""
Catálogo oficial de productos EcoFiver.
Este archivo es importado por TODOS los agentes.
"""

CATALOGO = {
    # precio_contado: se abona contra la instalación en el domicilio
    # precio_lista:   se abona en 6 cuotas sin interés con tarjeta de crédito
    "piscinas": [
        {"id": 1,  "modelo": "Minideck",                        "medida": "3,55x2,10 Deck / 3x2x70",     "precio_contado": 2490000,  "precio_lista": 4370000},
        {"id": 2,  "modelo": "Miniportante",                    "medida": "2,50x2,10x70",                 "precio_contado": 1990000,  "precio_lista": 3640000},
        {"id": 3,  "modelo": "Autoportante",                    "medida": "4,10x2,10x70",                 "precio_contado": 3000000,  "precio_lista": 4370000},
        {"id": 4,  "modelo": "Arco Romano Chico Recto",         "medida": "4,60x2,47x1,20",               "precio_contado": 3000000,  "precio_lista": 4370000},
        {"id": 5,  "modelo": "Arco Romano Chico C/Desnivel",    "medida": "4,60x2,35x1,10 a 1,30",        "precio_contado": 2990000,  "precio_lista": 4350000},
        {"id": 6,  "modelo": "Arco Romano Mediano Recto",       "medida": "6,40x2,94x1,40",               "precio_contado": 4900000,  "precio_lista": 7130000},
        {"id": 7,  "modelo": "Arco Romano Mediano C/Desnivel",  "medida": "7x3,35x1,25 a 1,70",           "precio_contado": 4490000,  "precio_lista": 7130000},
        {"id": 8,  "modelo": "Arco Romano Grande",              "medida": "8,10x3,35x1,25 a 1,80",        "precio_contado": 4800000,  "precio_lista": 6990000},
        {"id": 9,  "modelo": "Playa Humeda",                    "medida": "5,20x2,45x1,10 a 1,30",        "precio_contado": 3290000,  "precio_lista": 4790000},
        {"id": 10, "modelo": "Minimalista Chica",               "medida": "3,97x2,46x1,20",               "precio_contado": 2800000,  "precio_lista": 4080000},
        {"id": 11, "modelo": "Minimalista Mediana",             "medida": "5,50x2,90x1,50",               "precio_contado": 4425000,  "precio_lista": 6440000},
        {"id": 12, "modelo": "Minimalista Grande",              "medida": "6,40x3x1,40",                  "precio_contado": 3690000,  "precio_lista": 5370000},
        {"id": 13, "modelo": "Recta C/Mini Escalera",           "medida": "4,63x2,48x1,25",               "precio_contado": 3375000,  "precio_lista": 4910000},
        {"id": 14, "modelo": "Playa Humeda Chica C/Escalera",   "medida": "4,10x2,40x1,20",               "precio_contado": 2850000,  "precio_lista": 4150000},
        {"id": 15, "modelo": "Semi Playa Humeda C/Escalera",    "medida": "6,70x2,95x1,50",               "precio_contado": 3990000,  "precio_lista": 5810000},
        {"id": 16, "modelo": "Playa y Abanico",                 "medida": "9,20x3,80x1,25 a 1,80",        "precio_contado": 5500000,  "precio_lista": 8000000},
    ],
    "modulos_m2": [6, 12, 18, 24, 30, 36, 42, 48, 54, 60, 66, 72],
    # Precios módulos CONTADO (precio fijo para 6/12/18; proporcional al 18m² para mayores)
    "modulos_precios_contado": {6: 2990000, 12: 4980000, 18: 7480000},
    "modulos_precio_m2_base": 7480000 / 18,   # ~415.556/m² para >18m²
    # Precio módulos FINANCIADO: $510.000/m² (cualquier superficie, múltiplos de 6)
    "modulos_precio_m2_financiado": 510000,
    "flete_por_km": 3000,                  # general: piscinas (resto) y módulos
    "flete_alto_por_km": 5000,             # solo Arco Romano Grande y Playa y Abanico
    "flete_hidromasajes_por_km": 2000,     # hidromasajes / jacuzzis
    "flete_miniportante_por_km": 4000,     # ⚠️ valor histórico sin reconfirmar en la última corrección de tarifas
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
