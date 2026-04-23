#!/usr/bin/env python3
"""
wwlln_scraper.py — WWLLN Volcanic Lightning Scanner for Chile
=============================================================
Scrapes https://wwlln.net/USGS/Global/ for stroke counts near
43 Chilean volcanoes. Near-real-time data (WWLLN latency ~1-2 min).

Diseñado para discriminación operacional rayos/sismos en SERNAGEOMIN:
  - VERDE  : sin rayos en ≤20km  → señal sísmica no es rayo
  - AMARILLO: rayos mixtos       → posible tormenta eléctrica regional
  - ROJO   : concentración local → confirmar origen eléctrico

Algoritmo Georayos:
  ROJO    = inner>0 y outer==0, ó inner >= 2×outer
  AMARILLO = inner>0 y inner < 2×outer
  VERDE   = inner == 0

Salidas:
  docs/data/latest.json         — dashboard GitHub Pages
  datos/scan_YYYY-MM-DD_HHMM.json — archivo histórico
"""

import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("ERROR: pip install requests beautifulsoup4")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
WWLLN_URL = "https://wwlln.net/USGS/Global/"
KML_BASE  = "https://wwlln.net/USGS/Global/{}.kml"
KML_NS    = "http://www.opengis.net/kml/2.2"
TIMEOUT   = 15  # segundos por request

# Mapping: nombre interno → ID WWLLN (GVP)
VOLCANO_MAP: dict[str, str] = {
    "Taapaca":                 "1505-011",
    "Parinacota":              "1505-012",
    "Guallatiri":              "1505-02-",
    "Isluga":                  "1505-03-",
    "Irruputuncu":             "1505-04-",
    "Ollague":                 "1505-06-",
    "San Pedro":               "1505-07-",
    "Lascar":                  "1505-10-",
    "Tupungatito":             "1507-01-",
    "San Jose":                "1507-02-",
    "Tinguiririca":            "1507-03-",
    "Planchon-Peteroa":        "1507-04-",
    "Descabezado Grande":      "1507-05-",
    "Tatara-San Pedro":        "1507-062",
    "Laguna del Maule":        "1507-061",
    "Nevado de Longavi":       "1507-063",
    "Nevados de Chillan":      "1507-07-",
    "Antuco":                  "1507-08-",
    "Copahue":                 "1507-09-",
    "Callaqui":                "1507-091",
    "Lonquimay":               "1507-10-",
    "Llaima":                  "1507-11-",
    "Sollipulli":              "1507-111",
    "Villarrica":              "1507-12-",
    "Quetrupillan":            "1507-121",
    "Lanin":                   "1507-122",
    "Mocho-Choshuenco":        "1507-13-",
    "Carran - Los Venados":    "1507-14-",
    "Puyehue - Cordon Caulle": "1507-15-",
    "Antillanca - Casablanca": "1507-153",
    "Osorno":                  "1508-01-",
    "Calbuco":                 "1508-02-",
    "Yate":                    "1508-022",
    "Hornopiren":              "1508-023",
    "Huequi":                  "1508-03-",
    "Michinmahuida":           "1508-04-",
    "Chaiten":                 "1508-041",
    "Corcovado":               "1508-05-",
    "Melimoyu":                "1508-052",
    "Mentolat":                "1508-054",
    "Cay":                     "1508-055",
    "Maca":                    "1508-056",
    "Hudson":                  "1508-057",
    # Guatemala
    "Acatenango":              "1402-09-",
    "Fuego":                   "1402-10-",
    "Agua":                    "1402-111",
}

WANTED_IDS = set(VOLCANO_MAP.values())


# ---------------------------------------------------------------------------
# Georayos
# ---------------------------------------------------------------------------
def classify(inner: int, outer: int) -> str:
    if inner == 0:
        return "GREEN"
    if outer == 0 or inner >= 2 * outer:
        return "RED"
    return "YELLOW"


# ---------------------------------------------------------------------------
# Scrape tabla HTML
# ---------------------------------------------------------------------------
def fetch_wwlln_table(session: requests.Session) -> dict[str, dict]:
    """
    Una sola petición GET. Retorna dict keyed por wwlln_id:
      {inner, outer, lat, lon}
    donde inner = strokes <20km, outer = strokes 20-100km.
    """
    resp = session.get(WWLLN_URL, timeout=TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    table = soup.find("table")
    if not table:
        raise RuntimeError("No se encontró tabla en la página WWLLN")

    results: dict[str, dict] = {}
    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 8:
            continue
        vnum = cells[0].get_text(strip=True)
        if vnum not in WANTED_IDS:
            continue
        try:
            lat       = float(cells[4].get_text(strip=True))
            lon       = float(cells[5].get_text(strip=True))
            inner     = int(cells[6].get_text(strip=True))
            total_100 = int(cells[7].get_text(strip=True))
        except (ValueError, IndexError):
            continue
        results[vnum] = {
            "inner": inner,
            "outer": max(0, total_100 - inner),  # solo anillo 20-100km
            "lat":   lat,
            "lon":   lon,
        }

    print(f"[INFO] Tabla WWLLN: {len(results)}/{len(WANTED_IDS)} volcanes chilenos")
    return results


# ---------------------------------------------------------------------------
# Parseo KML — posiciones individuales de rayos
# ---------------------------------------------------------------------------
def parse_kml_strokes(kml_text: str) -> list[dict]:
    """Extrae coordenadas de cada rayo desde el KML."""
    positions: list[dict] = []
    try:
        root = ET.fromstring(kml_text)
        ns = KML_NS
        for folder in root.iter(f"{{{ns}}}Folder"):
            name_el = folder.find(f"{{{ns}}}name")
            if name_el is None:
                continue
            fname = (name_el.text or "").strip()
            if fname.startswith("Inner"):
                ring = "inner"
            elif fname.startswith("Outer"):
                ring = "outer"
            else:
                continue
            for pm in folder.findall(f"{{{ns}}}Placemark"):
                coords_el = pm.find(f".//{{{ns}}}coordinates")
                if coords_el is not None and coords_el.text:
                    parts = coords_el.text.strip().split(",")
                    if len(parts) >= 2:
                        try:
                            lon_s, lat_s = float(parts[0]), float(parts[1])
                            positions.append({"lat": lat_s, "lon": lon_s, "ring": ring})
                        except ValueError:
                            pass
    except ET.ParseError as e:
        print(f"[WARN] KML parse error: {e}")
    return positions


# ---------------------------------------------------------------------------
# Descarga paralela de KMLs (solo volcanes con rayos activos)
# ---------------------------------------------------------------------------
def download_kml_positions(
    active_ids: list[str], session: requests.Session
) -> dict[str, list[dict]]:
    stroke_map: dict[str, list[dict]] = {}
    if not active_ids:
        return stroke_map

    def fetch_one(wwlln_id: str) -> tuple[str, list[dict]]:
        url = KML_BASE.format(wwlln_id)
        try:
            r = session.get(url, timeout=TIMEOUT)
            r.raise_for_status()
            return wwlln_id, parse_kml_strokes(r.text)
        except Exception as exc:
            print(f"[WARN] KML {wwlln_id}: {exc}")
            return wwlln_id, []

    workers = min(8, len(active_ids))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_one, vid): vid for vid in active_ids}
        for fut in as_completed(futures):
            vid, positions = fut.result()
            stroke_map[vid] = positions

    print(f"[INFO] KMLs descargados: {len(active_ids)} volcán(es) activo(s)")
    return stroke_map


# ---------------------------------------------------------------------------
# Construir resultados
# ---------------------------------------------------------------------------
def build_results(
    table_data: dict[str, dict],
    stroke_positions: dict[str, list[dict]],
) -> list[dict]:
    results = []
    for name, wwlln_id in VOLCANO_MAP.items():
        row = table_data.get(wwlln_id)
        if row is None:
            print(f"[WARN] {name} ({wwlln_id}) no encontrado en tabla WWLLN")
            inner, outer, lat, lon = 0, 0, None, None
        else:
            inner, outer, lat, lon = row["inner"], row["outer"], row["lat"], row["lon"]

        results.append({
            "volcano":          name,
            "wwlln_id":         wwlln_id,
            "lat":              lat,
            "lon":              lon,
            "inner_strokes":    inner,
            "outer_strokes":    outer,
            "alert":            classify(inner, outer),
            "stroke_positions": stroke_positions.get(wwlln_id, []),
        })
    return results


# ---------------------------------------------------------------------------
# Guardar salidas
# ---------------------------------------------------------------------------
def save_outputs(
    results: list[dict], scan_time: datetime, script_dir: Path
) -> None:
    red    = sum(1 for r in results if r["alert"] == "RED")
    yellow = sum(1 for r in results if r["alert"] == "YELLOW")
    green  = sum(1 for r in results if r["alert"] == "GREEN")

    payload = {
        "scan_utc":        scan_time.isoformat(),
        "source":          "WWLLN",
        "window_hours":    1,
        "total_volcanoes": len(results),
        "red_alerts":      red,
        "yellow_alerts":   yellow,
        "green_alerts":    green,
        "volcanoes":       results,
    }

    # GitHub Pages
    docs_data = script_dir / "docs" / "data"
    docs_data.mkdir(parents=True, exist_ok=True)
    with open(docs_data / "latest.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"[INFO] latest.json → {docs_data / 'latest.json'}")

    # Archivo histórico
    datos_dir = script_dir / "datos"
    datos_dir.mkdir(parents=True, exist_ok=True)
    fname = f"scan_{scan_time:%Y-%m-%d_%H%M}.json"
    with open(datos_dir / fname, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"[INFO] Archivo → {datos_dir / fname}")


# ---------------------------------------------------------------------------
# Resumen en consola
# ---------------------------------------------------------------------------
def print_summary(results: list[dict], scan_time: datetime) -> None:
    sep = "=" * 72
    print(f"\n{sep}")
    print(f"  GEORAYOS — WWLLN Volcanic Lightning Scanner")
    print(f"  UTC: {scan_time:%Y-%m-%d %H:%M}  |  Ventana: última hora")
    print(sep)
    print(f"  {'Volcán':<28} {'Alerta':>8} {'≤20km':>6} {'20-100km':>9}")
    print(f"  {'-'*28} {'-'*8} {'-'*6} {'-'*9}")

    order = {"RED": 0, "YELLOW": 1, "GREEN": 2}
    for r in sorted(results, key=lambda r: order.get(r["alert"], 3)):
        tag    = r["alert"]
        marker = " ***" if tag == "RED" else "  * " if tag == "YELLOW" else "    "
        print(f"  {r['volcano']:<28} {tag:>8} {r['inner_strokes']:>6} {r['outer_strokes']:>9}{marker}")

    red    = sum(1 for r in results if r["alert"] == "RED")
    yellow = sum(1 for r in results if r["alert"] == "YELLOW")
    green  = sum(1 for r in results if r["alert"] == "GREEN")
    print(sep)
    print(f"  Resumen: {red} ROJO  |  {yellow} AMARILLO  |  {green} VERDE")
    print(f"{sep}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    t0 = datetime.now(timezone.utc)

    session = requests.Session()
    session.headers.update({
        "User-Agent": "LightningBot/2.0 SERNAGEOMIN-Georayos"
    })

    print("[1/3] Scraping tabla WWLLN...")
    table_data = fetch_wwlln_table(session)

    active_ids = [vid for vid, row in table_data.items() if row["inner"] > 0]
    print(f"[2/3] Descargando KMLs ({len(active_ids)} volcán(es) con rayos)...")
    stroke_positions = download_kml_positions(active_ids, session)

    print("[3/3] Generando resultados...")
    results = build_results(table_data, stroke_positions)
    save_outputs(results, t0, Path(__file__).resolve().parent)
    print_summary(results, t0)

    elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
    print(f"[OK] Completado en {elapsed:.1f}s")

    red_count = sum(1 for r in results if r["alert"] == "RED")
    if red_count:
        print(f"[ALERTA] {red_count} volcán(es) con rayos en anillo interior!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
