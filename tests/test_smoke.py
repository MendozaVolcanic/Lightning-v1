"""
Smoke tests para Lightning-v1.
Cubre la lógica pura (Georayos, dedup, parsing, distancia) sin tocar la red.
"""

import sys
from pathlib import Path

# Permitir import de módulos del proyecto sin instalar como paquete
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from volcanoes import VOLCANOES, WWLLN_ID_TO_NAME
from wwlln_scraper import classify as classify_wwlln, parse_kml_strokes
from glm_scraper import haversine_km, classify as classify_glm
from merger import combined_alert


# ---------------------------------------------------------------------------
# volcanoes.py — fuente única de verdad
# ---------------------------------------------------------------------------
def test_volcanoes_count_57():
    assert len(VOLCANOES) == 57, f"Esperamos 57, tenemos {len(VOLCANOES)}"


def test_volcanoes_format_valido():
    for name, info in VOLCANOES.items():
        assert isinstance(name, str) and name, f"nombre invalido: {name!r}"
        assert len(info) == 3, f"{name}: tupla debe ser (gvp_id, lat, lon)"
        gvp_id, lat, lon = info
        assert isinstance(gvp_id, str) and len(gvp_id) == 8, f"{name}: gvp_id={gvp_id!r}"
        assert -90 <= lat <= 90, f"{name}: lat fuera de rango ({lat})"
        assert -180 <= lon <= 180, f"{name}: lon fuera de rango ({lon})"


def test_volcanoes_ids_unicos():
    ids = [info[0] for info in VOLCANOES.values()]
    assert len(ids) == len(set(ids)), "GVP IDs duplicados"
    assert len(WWLLN_ID_TO_NAME) == len(VOLCANOES), "Mapeo inverso roto"


def test_volcanoes_chile_43():
    """43 volcanes chilenos esperados (GVP empiezan con 1505/1507/1508)."""
    chile = [n for n, (gid, _, _) in VOLCANOES.items()
             if gid.startswith(("1505-", "1507-", "1508-"))]
    assert len(chile) == 43, f"Esperamos 43 chilenos, hay {len(chile)}"


# ---------------------------------------------------------------------------
# Algoritmo Georayos (clasificación por fuente)
# ---------------------------------------------------------------------------
def test_georayos_green_sin_inner():
    assert classify_wwlln(0, 0) == "GREEN"
    assert classify_wwlln(0, 999) == "GREEN"
    assert classify_glm(0, 0) == "GREEN"


def test_georayos_red_solo_inner():
    """Inner > 0 con outer = 0 → RED (rayo aislado en cráter)."""
    assert classify_wwlln(1, 0) == "RED"
    assert classify_wwlln(5, 0) == "RED"


def test_georayos_red_concentracion_volcanica():
    """Inner ≥ 2*outer → RED (concentración volcánica)."""
    assert classify_wwlln(10, 5) == "RED"
    assert classify_wwlln(10, 4) == "RED"
    assert classify_wwlln(100, 50) == "RED"


def test_georayos_yellow_tormenta_regional():
    """Inner > 0 pero inner < 2*outer → YELLOW (tormenta regional)."""
    assert classify_wwlln(1, 1) == "YELLOW"
    assert classify_wwlln(1, 10) == "YELLOW"
    assert classify_wwlln(5, 100) == "YELLOW"
    assert classify_glm(3, 11) == "YELLOW"  # caso real Maderas (NIC)


# ---------------------------------------------------------------------------
# Alerta combinada (merger)
# ---------------------------------------------------------------------------
def test_combined_red_solo_si_ambas_red():
    assert combined_alert("RED", "RED") == "RED"
    # Una sola RED ≠ RED combinado
    assert combined_alert("RED", "YELLOW") == "YELLOW"
    assert combined_alert("RED", "GREEN") == "YELLOW"
    assert combined_alert("YELLOW", "RED") == "YELLOW"


def test_combined_yellow_si_cualquiera_amarilla():
    assert combined_alert("YELLOW", "GREEN") == "YELLOW"
    assert combined_alert("GREEN", "YELLOW") == "YELLOW"
    assert combined_alert("YELLOW", "YELLOW") == "YELLOW"


def test_combined_green_si_ambas_green_o_ausentes():
    assert combined_alert("GREEN", "GREEN") == "GREEN"
    assert combined_alert(None, "GREEN") == "GREEN"
    assert combined_alert("GREEN", None) == "GREEN"
    assert combined_alert(None, None) == "GREEN"


# ---------------------------------------------------------------------------
# Haversine
# ---------------------------------------------------------------------------
def test_haversine_punto_mismo():
    assert haversine_km(0, 0, 0, 0) == 0
    assert haversine_km(-33.45, -70.66, -33.45, -70.66) == 0


def test_haversine_distancia_conocida_santiago_buenos_aires():
    # ~1138 km según referencias geodésicas
    d = haversine_km(-33.45, -70.66, -34.61, -58.38)
    assert 1100 < d < 1200, f"esperado ~1138, got {d:.0f}"


def test_haversine_cuarto_circunferencia():
    # Ecuador → 90°E: ~10 007 km (¼ de la circunferencia terrestre)
    d = haversine_km(0, 0, 0, 90)
    assert 9900 < d < 10100, f"esperado ~10007, got {d:.0f}"


def test_haversine_radio_interior_volcan():
    """A ~5.5 km de Fuego, debe quedar dentro del anillo interior (20 km)."""
    fuego_lat, fuego_lon = VOLCANOES["Fuego"][1], VOLCANOES["Fuego"][2]
    # +0.05° lat ≈ 5.5 km
    d = haversine_km(fuego_lat + 0.05, fuego_lon, fuego_lat, fuego_lon)
    assert d < 20
    # +1° lat ≈ 111 km → fuera del anillo exterior
    d2 = haversine_km(fuego_lat + 1.0, fuego_lon, fuego_lat, fuego_lon)
    assert d2 > 100


# ---------------------------------------------------------------------------
# Parseo de KML (formato real de WWLLN)
# ---------------------------------------------------------------------------
def test_kml_vacio_retorna_lista_vacia():
    kml = '''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document><name>Sin actividad</name></Document>
</kml>'''
    assert parse_kml_strokes(kml) == []


def test_kml_parse_inner_stroke():
    """KML con 1 placemark en Inner ring debe extraer todos los metadatos."""
    kml = '''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Folder>
      <name>Inner Ring (20 km)</name>
      <Placemark>
        <name>2026-04-24T13:05:22</name>
        <description><![CDATA[Lat: 14.473, Lon: -90.881, Residual: 4.2 us, detected at 7 WWLLN stations]]></description>
        <Point><coordinates>-90.881,14.473,0</coordinates></Point>
      </Placemark>
    </Folder>
  </Document>
</kml>'''
    strokes = parse_kml_strokes(kml)
    assert len(strokes) == 1
    s = strokes[0]
    assert s["ring"] == "inner"
    assert abs(s["lat"] - 14.473) < 0.001
    assert abs(s["lon"] - (-90.881)) < 0.001
    assert s["residual_us"] == 4.2
    assert s["stations"] == 7
    assert s["time"] and "2026-04-24" in s["time"]


def test_kml_parse_outer_stroke():
    """Folder con name 'Outer' debe etiquetar el ring correctamente."""
    kml = '''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Folder>
      <name>Outer Ring (100 km)</name>
      <Placemark>
        <Point><coordinates>-70.5,-37.4,0</coordinates></Point>
      </Placemark>
    </Folder>
  </Document>
</kml>'''
    strokes = parse_kml_strokes(kml)
    assert len(strokes) == 1
    assert strokes[0]["ring"] == "outer"


def test_kml_ignora_folders_desconocidos():
    """Un Folder que no sea Inner/Outer debe ignorarse."""
    kml = '''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Folder>
      <name>Random metadata folder</name>
      <Placemark><Point><coordinates>0,0,0</coordinates></Point></Placemark>
    </Folder>
  </Document>
</kml>'''
    assert parse_kml_strokes(kml) == []
