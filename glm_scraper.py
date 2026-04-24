#!/usr/bin/env python3
"""
glm_scraper.py — GOES-19 GLM Volcanic Lightning Scanner
========================================================
Descarga archivos GLM L2 LCFA (Lightning Cluster Filter Algorithm)
desde el bucket público de NOAA en AWS S3, y filtra cada flash
por distancia haversine a los 46 volcanes monitoreados.

Ventana: últimos GLM_WINDOW_MIN minutos.
Cadencia típica: cada 5–10 min desde GitHub Actions.
Satélite: GOES-19 (operacional GOES-East desde 2025).

Anillos (iguales a WWLLN):
  inner  ≤ 20 km del cráter
  outer  20–100 km

Clasificación Georayos: idéntica a wwlln_scraper.py.

Salidas:
  docs/data/glm_latest.json — feed GLM puro (consumido por merger.py)
"""

import json
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import requests
    import xarray as xr
except ImportError:
    print("ERROR: pip install requests xarray netCDF4 h5netcdf")
    sys.exit(1)

from volcanoes import VOLCANOES

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
S3_HOST        = "https://noaa-goes19.s3.amazonaws.com"
S3_PRODUCT     = "GLM-L2-LCFA"
GLM_WINDOW_MIN = 15            # ventana en minutos (cuánto pasado mirar)
INNER_KM       = 20
OUTER_KM       = 100
HTTP_TIMEOUT   = 20

# Concurrencia
LIST_WORKERS     = 3            # listados de S3 (pocas horas, pocos workers)
DOWNLOAD_WORKERS = 12           # descargas paralelas


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia great-circle en km."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def classify(inner: int, outer: int) -> str:
    if inner == 0:
        return "GREEN"
    if outer == 0 or inner >= 2 * outer:
        return "RED"
    return "YELLOW"


# ---------------------------------------------------------------------------
# Listado de archivos en S3 (XML bucket listing)
# ---------------------------------------------------------------------------
def _list_hour(session: requests.Session, dt: datetime) -> list[str]:
    """
    Lista las keys de archivos GLM L2 LCFA para una hora específica.
    S3 limit es 1000 keys; una hora tiene ~180 archivos → OK.
    """
    doy = dt.timetuple().tm_yday
    prefix = f"{S3_PRODUCT}/{dt.year}/{doy:03d}/{dt.hour:02d}/"
    url = f"{S3_HOST}/?list-type=2&prefix={prefix}"
    try:
        r = session.get(url, timeout=HTTP_TIMEOUT)
        r.raise_for_status()
    except Exception as exc:
        print(f"[WARN] list {prefix}: {exc}")
        return []

    # Parseo XML sin dependencias extras
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(r.text)
    except ET.ParseError as e:
        print(f"[WARN] parse listing {prefix}: {e}")
        return []

    ns = "{http://s3.amazonaws.com/doc/2006-03-01/}"
    return [c.findtext(f"{ns}Key") for c in root.findall(f"{ns}Contents")]


def list_window_files(
    session: requests.Session, now: datetime, window_min: int
) -> list[str]:
    """Archivos GLM en la ventana [now-window_min, now]."""
    start = now - timedelta(minutes=window_min)

    # Horas únicas que cubren la ventana (máx 2 en ventanas ≤60min)
    hours: list[datetime] = []
    t = start.replace(minute=0, second=0, microsecond=0)
    while t <= now:
        hours.append(t)
        t += timedelta(hours=1)

    keys: list[str] = []
    with ThreadPoolExecutor(max_workers=min(LIST_WORKERS, len(hours))) as pool:
        for res in pool.map(lambda h: _list_hour(session, h), hours):
            keys.extend(res)

    # Filtrar por timestamp de nombre:
    # OR_GLM-L2-LCFA_G19_sYYYYDDDHHMMSSms_eYYYYDDDHHMMSSms_cYYYYDDDHHMMSSms.nc
    filtered = []
    for k in keys:
        fname = k.split("/")[-1]
        try:
            s_str = fname.split("_s")[1][:14]  # YYYYDDDHHMMSSM
            # Solo YYYYDDDHHMMSS (13 chars); el último es decisegundo
            dt = datetime.strptime(s_str[:13], "%Y%j%H%M%S").replace(tzinfo=timezone.utc)
        except (IndexError, ValueError):
            continue
        if start <= dt <= now:
            filtered.append(k)
    return sorted(filtered)


# ---------------------------------------------------------------------------
# Descarga + parseo de archivos GLM
# ---------------------------------------------------------------------------
def _download_and_parse(session: requests.Session, key: str) -> list[dict]:
    """
    Descarga un archivo GLM L2 LCFA y extrae cada flash:
      {lat, lon, time_iso, energy_j, area_m2}
    """
    url = f"{S3_HOST}/{key}"
    try:
        r = session.get(url, timeout=HTTP_TIMEOUT)
        r.raise_for_status()
    except Exception as exc:
        print(f"[WARN] download {key}: {exc}")
        return []

    flashes: list[dict] = []
    try:
        # xarray soporta archivos en memoria via io.BytesIO
        import io
        ds = xr.open_dataset(io.BytesIO(r.content), engine="h5netcdf")
    except Exception as exc:
        print(f"[WARN] open {key}: {exc}")
        return []

    try:
        if "flash_lat" not in ds or "flash_lon" not in ds:
            return []
        lats = ds["flash_lat"].values
        lons = ds["flash_lon"].values
        energies = ds["flash_energy"].values if "flash_energy" in ds else [None] * len(lats)
        areas    = ds["flash_area"].values   if "flash_area"   in ds else [None] * len(lats)

        # Timestamp: product_time (escalar) + flash_time_offset_of_first_event (por flash, seg)
        try:
            product_time = ds["product_time"].values
            # product_time en epoch J2000 nanoseconds → convertir a datetime UTC
            base = _decode_glm_time(ds["product_time"])
        except Exception:
            base = datetime.now(timezone.utc)

        offsets = ds["flash_time_offset_of_first_event"].values if "flash_time_offset_of_first_event" in ds else [0] * len(lats)

        for i in range(len(lats)):
            try:
                lat = float(lats[i]); lon = float(lons[i])
            except (TypeError, ValueError):
                continue
            if math.isnan(lat) or math.isnan(lon):
                continue
            try:
                off_s = float(offsets[i])
            except (TypeError, ValueError):
                off_s = 0.0
            t_iso = (base + timedelta(seconds=off_s)).isoformat(timespec="seconds")
            flashes.append({
                "lat":      lat,
                "lon":      lon,
                "time":     t_iso,
                "energy_j": None if energies[i] is None or (isinstance(energies[i], float) and math.isnan(energies[i])) else float(energies[i]),
                "area_m2":  None if areas[i]    is None or (isinstance(areas[i], float) and math.isnan(areas[i]))       else float(areas[i]),
            })
    finally:
        ds.close()
    return flashes


def _decode_glm_time(var) -> datetime:
    """GLM product_time: segundos desde 2000-01-01 12:00:00 UTC (J2000)."""
    J2000 = datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    try:
        val = float(var.values)
        return J2000 + timedelta(seconds=val)
    except Exception:
        return datetime.now(timezone.utc)


def download_all_flashes(
    session: requests.Session, keys: list[str]
) -> list[dict]:
    all_flashes: list[dict] = []
    if not keys:
        return all_flashes

    workers = min(DOWNLOAD_WORKERS, len(keys))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_download_and_parse, session, k) for k in keys]
        for fut in as_completed(futures):
            all_flashes.extend(fut.result())
    return all_flashes


# ---------------------------------------------------------------------------
# Filtrado por volcán
# ---------------------------------------------------------------------------
def filter_by_volcano(flashes: list[dict]) -> list[dict]:
    """Filtra flashes a ≤ OUTER_KM de cada volcán, asigna anillo."""
    results: list[dict] = []
    for name, (wwlln_id, vlat, vlon) in VOLCANOES.items():
        inner = 0
        outer = 0
        positions: list[dict] = []
        for f in flashes:
            d = haversine_km(vlat, vlon, f["lat"], f["lon"])
            if d > OUTER_KM:
                continue
            ring = "inner" if d <= INNER_KM else "outer"
            if ring == "inner":
                inner += 1
            else:
                outer += 1
            positions.append({
                "lat":      f["lat"],
                "lon":      f["lon"],
                "ring":     ring,
                "time":     f["time"],
                "energy_j": f["energy_j"],
                "area_m2":  f["area_m2"],
            })
        results.append({
            "volcano":         name,
            "wwlln_id":        wwlln_id,
            "lat":             vlat,
            "lon":             vlon,
            "inner_flashes":   inner,
            "outer_flashes":   outer,
            "alert":           classify(inner, outer),
            "flash_positions": positions,
        })
    return results


# ---------------------------------------------------------------------------
# Salida
# ---------------------------------------------------------------------------
def save_output(results: list[dict], scan_time: datetime, script_dir: Path) -> None:
    red    = sum(1 for r in results if r["alert"] == "RED")
    yellow = sum(1 for r in results if r["alert"] == "YELLOW")
    green  = sum(1 for r in results if r["alert"] == "GREEN")

    payload = {
        "scan_utc":        scan_time.isoformat(),
        "source":          "GLM-G19",
        "window_minutes":  GLM_WINDOW_MIN,
        "total_volcanoes": len(results),
        "red_alerts":      red,
        "yellow_alerts":   yellow,
        "green_alerts":    green,
        "volcanoes":       results,
    }

    docs_data = script_dir / "docs" / "data"
    docs_data.mkdir(parents=True, exist_ok=True)
    with open(docs_data / "glm_latest.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"[INFO] glm_latest.json → {docs_data / 'glm_latest.json'}")


def print_summary(results: list[dict], scan_time: datetime, n_flashes: int) -> None:
    active = [r for r in results if r["inner_flashes"] > 0 or r["outer_flashes"] > 0]
    sep = "=" * 72
    print(f"\n{sep}")
    print(f"  GLM-G19 Volcanic Lightning Scanner")
    print(f"  UTC: {scan_time:%Y-%m-%d %H:%M}  |  Ventana: {GLM_WINDOW_MIN} min")
    print(f"  Flashes descargados globalmente: {n_flashes}")
    print(sep)
    if not active:
        print("  (sin actividad en ningún volcán monitoreado)")
    else:
        print(f"  {'Volcán':<28} {'Alerta':>8} {'≤20km':>6} {'20-100km':>9}")
        order = {"RED": 0, "YELLOW": 1, "GREEN": 2}
        for r in sorted(active, key=lambda r: order.get(r["alert"], 3)):
            print(f"  {r['volcano']:<28} {r['alert']:>8} {r['inner_flashes']:>6} {r['outer_flashes']:>9}")
    print(sep + "\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    t0 = datetime.now(timezone.utc)

    session = requests.Session()
    session.headers.update({"User-Agent": "LightningBot/2.0 SERNAGEOMIN-Georayos GLM"})

    print(f"[1/3] Listando archivos GLM de los últimos {GLM_WINDOW_MIN} min...")
    keys = list_window_files(session, t0, GLM_WINDOW_MIN)
    print(f"      {len(keys)} archivo(s) encontrado(s)")

    if not keys:
        print("[WARN] Sin archivos en la ventana (posible retraso de NOAA o reloj S3)")

    print(f"[2/3] Descargando y parseando {len(keys)} archivo(s)...")
    t_dl = time.time()
    flashes = download_all_flashes(session, keys)
    print(f"      {len(flashes)} flash(es) extraídos en {time.time() - t_dl:.1f}s")

    print("[3/3] Filtrando por volcán...")
    results = filter_by_volcano(flashes)

    save_output(results, t0, Path(__file__).resolve().parent)
    print_summary(results, t0, len(flashes))

    elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
    print(f"[OK] GLM scan completado en {elapsed:.1f}s")

    red_count = sum(1 for r in results if r["alert"] == "RED")
    if red_count:
        print(f"[ALERTA] GLM: {red_count} volcán(es) con rayos en anillo interior")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        # En producción no queremos romper el workflow si GLM falla.
        # Escribimos un JSON vacío y salimos con éxito.
        print(f"[ERROR] GLM scraper falló: {exc}")
        empty = {
            "scan_utc": datetime.now(timezone.utc).isoformat(),
            "source": "GLM-G19",
            "window_minutes": GLM_WINDOW_MIN,
            "total_volcanoes": len(VOLCANOES),
            "red_alerts": 0, "yellow_alerts": 0, "green_alerts": len(VOLCANOES),
            "error": str(exc),
            "volcanoes": [
                {
                    "volcano": name, "wwlln_id": info[0],
                    "lat": info[1], "lon": info[2],
                    "inner_flashes": 0, "outer_flashes": 0,
                    "alert": "GREEN", "flash_positions": [],
                }
                for name, info in VOLCANOES.items()
            ],
        }
        out = Path(__file__).resolve().parent / "docs" / "data" / "glm_latest.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(empty, indent=2, ensure_ascii=False), encoding="utf-8")
        sys.exit(0)
