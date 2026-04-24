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
  docs/data/wwlln_latest.json — feed WWLLN puro (consumido por merger.py)
  datos/alert_history.csv     — CSV acumulativo permanente (WWLLN)

El historial de scans y el índice los escribe merger.py con datos
combinados WWLLN+GLM.
"""

import csv
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
import xml.etree.ElementTree as ET

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("ERROR: pip install requests beautifulsoup4")
    sys.exit(1)

from volcanoes import VOLCANOES

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
WWLLN_URL = "https://wwlln.net/USGS/Global/"
KML_BASE  = "https://wwlln.net/USGS/Global/{}.kml"
KML_NS    = "http://www.opengis.net/kml/2.2"
TIMEOUT   = 15  # segundos por request

# Mapping: nombre interno → ID WWLLN (GVP), derivado de volcanoes.py
VOLCANO_MAP: dict[str, str] = {name: info[0] for name, info in VOLCANOES.items()}
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
_RE_RESIDUAL = re.compile(r"Residual:\s*([\d.]+)\s*us")
_RE_STATIONS = re.compile(r"detected at\s+(\d+)\s+WWLLN")


def parse_kml_strokes(kml_text: str) -> list[dict]:
    """
    Extrae cada rayo desde el KML con todos sus metadatos:
      lat, lon, ring (inner/outer), time, residual_us, stations
    """
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
                if coords_el is None or not coords_el.text:
                    continue
                parts = coords_el.text.strip().split(",")
                if len(parts) < 2:
                    continue
                try:
                    lon_s, lat_s = float(parts[0]), float(parts[1])
                except ValueError:
                    continue

                # Timestamp está en <name>
                stroke_time = None
                pm_name = pm.find(f"{{{ns}}}name")
                if pm_name is not None and pm_name.text:
                    stroke_time = pm_name.text.strip()

                # Residual y estaciones están en <description> CDATA
                residual_us = None
                stations = None
                desc_el = pm.find(f"{{{ns}}}description")
                if desc_el is not None and desc_el.text:
                    m = _RE_RESIDUAL.search(desc_el.text)
                    if m:
                        residual_us = float(m.group(1))
                    m = _RE_STATIONS.search(desc_el.text)
                    if m:
                        stations = int(m.group(1))

                positions.append({
                    "lat":         lat_s,
                    "lon":         lon_s,
                    "ring":        ring,
                    "time":        stroke_time,
                    "residual_us": residual_us,
                    "stations":    stations,
                })
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

    # 1. Feed WWLLN puro → merger.py lo lee y combina con GLM
    docs_data = script_dir / "docs" / "data"
    docs_data.mkdir(parents=True, exist_ok=True)
    with open(docs_data / "wwlln_latest.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"[INFO] wwlln_latest.json → {docs_data / 'wwlln_latest.json'}")

    # 2. CSV acumulativo permanente (histórico solo de WWLLN)
    datos_dir = script_dir / "datos"
    datos_dir.mkdir(parents=True, exist_ok=True)
    _append_csv(results, scan_time, datos_dir)


def _append_csv(results: list[dict], scan_time: datetime, datos_dir: Path) -> None:
    """Agrega una fila por volcán al CSV histórico acumulativo."""
    csv_path = datos_dir / "alert_history.csv"
    write_header = not csv_path.exists()
    with open(csv_path, "a", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        if write_header:
            writer.writerow([
                "scan_utc", "volcano", "wwlln_id",
                "inner_strokes", "outer_strokes", "alert", "n_stroke_positions"
            ])
        for r in results:
            writer.writerow([
                scan_time.isoformat(),
                r["volcano"],
                r["wwlln_id"],
                r["inner_strokes"],
                r["outer_strokes"],
                r["alert"],
                len(r.get("stroke_positions", [])),
            ])
    print(f"[INFO] CSV histórico → datos/alert_history.csv")


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

    active_ids = [vid for vid, row in table_data.items() if row["inner"] > 0 or row["outer"] > 0]
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
