"""
Coordenadas de volcanes: contra el catálogo GVP y entre sí.

Por qué existe: hasta nov-2026 "Nevados de Chillan" estaba en -37,411, -71,352,
que es Antuco (a 1,3 km de la entrada "Antuco" y a 60 km del Chillán real). Los
anillos de 20 y 100 km se medían alrededor del volcán equivocado, así que el
conteo de rayos de Chillán era en realidad el de Antuco.

Referencias: Smithsonian GVP, Volcanoes of the World (servicio WFS
GVP-VOTW:Smithsonian_VOTW_Holocene_Volcanoes, consultado 20-11-2026).
"""

import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from glm_scraper import haversine_km
from volcanoes import VOLCANOES

# (número GVP, lat, lon) tal como los publica el GVP.
GVP_REF = {
    "Nevados de Chillan": (357070, -36.868, -71.378),
    "Antuco":             (357080, -37.406, -71.349),
}

# Fuego y Acatenango, el par real más cercano del catálogo, están a 3,2 km.
# Dos entradas a menos de 2 km son casi seguro el mismo edificio repetido.
DISTANCIA_MINIMA_KM = 2.0


def test_chillan_en_sus_coordenadas_gvp():
    _, lat, lon = VOLCANOES["Nevados de Chillan"]
    _, ref_lat, ref_lon = GVP_REF["Nevados de Chillan"]
    d = haversine_km(lat, lon, ref_lat, ref_lon)
    assert d < 2.0, f"Nevados de Chillan a {d:.1f} km de GVP 357070"


def test_antuco_en_sus_coordenadas_gvp():
    _, lat, lon = VOLCANOES["Antuco"]
    _, ref_lat, ref_lon = GVP_REF["Antuco"]
    d = haversine_km(lat, lon, ref_lat, ref_lon)
    assert d < 2.0, f"Antuco a {d:.1f} km de GVP 357080"


def test_sin_coordenadas_repetidas():
    coords = [(lat, lon) for _, lat, lon in VOLCANOES.values()]
    assert len(coords) == len(set(coords)), "Dos volcanes con la misma coordenada"


def test_distancia_minima_entre_volcanes():
    cerca = []
    for (n1, (_, la1, lo1)), (n2, (_, la2, lo2)) in itertools.combinations(VOLCANOES.items(), 2):
        d = haversine_km(la1, lo1, la2, lo2)
        if d < DISTANCIA_MINIMA_KM:
            cerca.append(f"{n1} / {n2}: {d:.2f} km")
    assert not cerca, "Volcanes casi superpuestos: " + "; ".join(cerca)
