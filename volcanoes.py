"""
volcanoes.py — Fuente única de los 46 volcanes monitoreados
=============================================================
Usado por wwlln_scraper.py y glm_scraper.py.

Formato:
  nombre: (gvp_id, lat, lon)

gvp_id = Global Volcanism Program (Smithsonian) número de volcán,
         el mismo que usa WWLLN en su tabla.
"""

# (gvp_id, lat, lon)
VOLCANOES: dict[str, tuple[str, float, float]] = {
    # Guatemala
    "Acatenango":              ("1402-09-",  14.501, -90.876),
    "Fuego":                   ("1402-10-",  14.473, -90.881),
    "Agua":                    ("1402-111",  14.466, -90.743),
    # Chile — Norte
    "Taapaca":                 ("1505-011", -18.109, -69.506),
    "Parinacota":              ("1505-012", -18.171, -69.145),
    "Guallatiri":              ("1505-02-", -18.428, -69.085),
    "Isluga":                  ("1505-03-", -19.167, -68.822),
    "Irruputuncu":             ("1505-04-", -20.733, -68.560),
    "Ollague":                 ("1505-06-", -21.307, -68.179),
    "San Pedro":               ("1505-07-", -21.885, -68.407),
    "Lascar":                  ("1505-10-", -23.367, -67.736),
    # Chile — Centro
    "Tupungatito":             ("1507-01-", -33.408, -69.822),
    "San Jose":                ("1507-02-", -33.787, -69.897),
    "Tinguiririca":            ("1507-03-", -34.808, -70.349),
    "Planchon-Peteroa":        ("1507-04-", -35.242, -70.572),
    "Descabezado Grande":      ("1507-05-", -35.604, -70.748),
    "Tatara-San Pedro":        ("1507-062", -35.998, -70.845),
    "Laguna del Maule":        ("1507-061", -36.071, -70.498),
    "Nevado de Longavi":       ("1507-063", -36.200, -71.170),
    "Nevados de Chillan":      ("1507-07-", -37.411, -71.352),
    "Antuco":                  ("1507-08-", -37.419, -71.341),
    "Copahue":                 ("1507-09-", -37.857, -71.168),
    "Callaqui":                ("1507-091", -37.926, -71.461),
    "Lonquimay":               ("1507-10-", -38.382, -71.585),
    "Llaima":                  ("1507-11-", -38.712, -71.734),
    "Sollipulli":              ("1507-111", -38.981, -71.516),
    "Villarrica":              ("1507-12-", -39.421, -71.939),
    "Quetrupillan":            ("1507-121", -39.532, -71.703),
    "Lanin":                   ("1507-122", -39.628, -71.479),
    "Mocho-Choshuenco":        ("1507-13-", -39.934, -72.003),
    "Carran - Los Venados":    ("1507-14-", -40.379, -72.105),
    "Puyehue - Cordon Caulle": ("1507-15-", -40.559, -72.125),
    "Antillanca - Casablanca": ("1507-153", -40.771, -72.153),
    # Chile — Sur / Austral
    "Osorno":                  ("1508-01-", -41.135, -72.497),
    "Calbuco":                 ("1508-02-", -41.329, -72.611),
    "Yate":                    ("1508-022", -41.755, -72.396),
    "Hornopiren":              ("1508-023", -41.874, -72.431),
    "Huequi":                  ("1508-03-", -42.378, -72.578),
    "Michinmahuida":           ("1508-04-", -42.790, -72.440),
    "Chaiten":                 ("1508-041", -42.839, -72.650),
    "Corcovado":               ("1508-05-", -43.192, -72.079),
    "Melimoyu":                ("1508-052", -44.081, -72.857),
    "Mentolat":                ("1508-054", -44.700, -73.082),
    "Cay":                     ("1508-055", -45.059, -72.984),
    "Maca":                    ("1508-056", -45.100, -73.174),
    "Hudson":                  ("1508-057", -45.900, -72.970),
}

# Mapeos derivados
WWLLN_ID_TO_NAME: dict[str, str] = {v[0]: k for k, v in VOLCANOES.items()}
VOLCANO_NAMES: list[str] = list(VOLCANOES.keys())
