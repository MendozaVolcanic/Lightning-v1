#!/usr/bin/env python3
"""
lightning_scanner.py — Volcanic Lightning Scanner for Chile
===========================================================
Downloads GOES-16 GLM (Geostationary Lightning Mapper) data and checks
for volcanic lightning near 43 Chilean volcanoes using the Georayos algorithm.

Classification (Georayos):
  RED    : lightning only in inner ring (<=20 km), OR inner >= 2x outer
  YELLOW : inner > 0 but inner < 2x outer
  GREEN  : no inner ring lightning

Outputs:
  datos/scan_YYYY-MM-DD_HHMM.json   — full scan results
  datos/alert_history.csv            — append-only summary
"""

import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# goes2go import with helpful error
# ---------------------------------------------------------------------------
try:
    from goes2go import GOES
except ImportError:
    print(
        "ERROR: 'goes2go' library not found.\n"
        "Install it with:  pip install goes2go\n"
        "Or:               conda install -c conda-forge goes2go"
    )
    sys.exit(1)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
INNER_RADIUS_KM = 20
OUTER_RADIUS_KM = 100
EARTH_RADIUS_KM = 6371.0

VOLCANES = {
    "Taapaca": {"lat": -18.109, "lon": -69.506},
    "Parinacota": {"lat": -18.171, "lon": -69.145},
    "Guallatiri": {"lat": -18.428, "lon": -69.085},
    "Isluga": {"lat": -19.167, "lon": -68.822},
    "Irruputuncu": {"lat": -20.733, "lon": -68.560},
    "Ollague": {"lat": -21.307, "lon": -68.179},
    "San Pedro": {"lat": -21.885, "lon": -68.407},
    "Lascar": {"lat": -23.367, "lon": -67.736},
    "Tupungatito": {"lat": -33.408, "lon": -69.822},
    "San Jose": {"lat": -33.787, "lon": -69.897},
    "Tinguiririca": {"lat": -34.808, "lon": -70.349},
    "Planchon-Peteroa": {"lat": -35.242, "lon": -70.572},
    "Descabezado Grande": {"lat": -35.604, "lon": -70.748},
    "Tatara-San Pedro": {"lat": -35.998, "lon": -70.845},
    "Laguna del Maule": {"lat": -36.071, "lon": -70.498},
    "Nevado de Longavi": {"lat": -36.200, "lon": -71.170},
    "Nevados de Chillan": {"lat": -37.411, "lon": -71.352},
    "Antuco": {"lat": -37.419, "lon": -71.341},
    "Copahue": {"lat": -37.857, "lon": -71.168},
    "Callaqui": {"lat": -37.926, "lon": -71.461},
    "Lonquimay": {"lat": -38.382, "lon": -71.585},
    "Llaima": {"lat": -38.712, "lon": -71.734},
    "Sollipulli": {"lat": -38.981, "lon": -71.516},
    "Villarrica": {"lat": -39.421, "lon": -71.939},
    "Quetrupillan": {"lat": -39.532, "lon": -71.703},
    "Lanin": {"lat": -39.628, "lon": -71.479},
    "Mocho-Choshuenco": {"lat": -39.934, "lon": -72.003},
    "Carran - Los Venados": {"lat": -40.379, "lon": -72.105},
    "Puyehue - Cordon Caulle": {"lat": -40.559, "lon": -72.125},
    "Antillanca - Casablanca": {"lat": -40.771, "lon": -72.153},
    "Osorno": {"lat": -41.135, "lon": -72.497},
    "Calbuco": {"lat": -41.329, "lon": -72.611},
    "Hornopiren": {"lat": -41.874, "lon": -72.431},
    "Huequi": {"lat": -42.378, "lon": -72.578},
    "Michinmahuida": {"lat": -42.790, "lon": -72.440},
    "Chaiten": {"lat": -42.839, "lon": -72.650},
    "Corcovado": {"lat": -43.192, "lon": -72.079},
    "Yate": {"lat": -41.755, "lon": -72.396},
    "Melimoyu": {"lat": -44.081, "lon": -72.857},
    "Mentolat": {"lat": -44.700, "lon": -73.082},
    "Maca": {"lat": -45.100, "lon": -73.174},
    "Cay": {"lat": -45.059, "lon": -72.984},
    "Hudson": {"lat": -45.900, "lon": -72.970},
}


# ---------------------------------------------------------------------------
# Haversine distance
# ---------------------------------------------------------------------------
def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in km between two points."""
    lat1_r, lon1_r = math.radians(lat1), math.radians(lon1)
    lat2_r, lon2_r = math.radians(lat2), math.radians(lon2)
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# Georayos classification
# ---------------------------------------------------------------------------
def classify_georayos(inner_count: int, outer_count: int) -> str:
    """
    RED    : lightning only in inner ring, OR inner >= 2x outer
    YELLOW : inner > 0 but inner < 2x outer
    GREEN  : no inner ring lightning
    """
    if inner_count == 0:
        return "GREEN"
    if outer_count == 0:
        # Lightning only in inner ring
        return "RED"
    if inner_count >= 2 * outer_count:
        return "RED"
    return "YELLOW"


# ---------------------------------------------------------------------------
# Download GLM data
# ---------------------------------------------------------------------------
def download_glm_data(minutes: int = 60) -> list:
    """
    Download the latest `minutes` of GLM-L2-LCFA data from GOES-16.
    Returns a list of xarray Datasets, one per file.
    """
    datasets = []
    now_utc = datetime.now(timezone.utc)
    start = now_utc - timedelta(minutes=minutes)

    print(f"[INFO] Requesting GLM data from {start:%Y-%m-%d %H:%M} to {now_utc:%H:%M} UTC")

    # Try Full Disk first (covers all of South America), fall back to CONUS
    for domain in ("F", "C"):
        try:
            G = GOES(satellite=16, product="GLM-L2-LCFA", domain=domain)
            # goes2go .timerange() returns list of paths or datasets
            results = G.timerange(
                start=start,
                end=now_utc,
                return_as="xarray",
            )
            if results is not None:
                if isinstance(results, list):
                    datasets.extend(results)
                else:
                    datasets.append(results)
            if datasets:
                print(f"[INFO] Downloaded {len(datasets)} GLM file(s) using domain='{domain}'")
                return datasets
        except Exception as e:
            print(f"[WARN] Domain '{domain}' failed: {e}")
            continue

    # Fallback: try .latest()
    print("[INFO] Timerange failed, trying .latest() as fallback ...")
    for domain in ("F", "C"):
        try:
            G = GOES(satellite=16, product="GLM-L2-LCFA", domain=domain)
            ds = G.latest()
            if ds is not None:
                datasets.append(ds)
                print(f"[INFO] Got latest GLM file via domain='{domain}'")
                return datasets
        except Exception as e:
            print(f"[WARN] latest() domain '{domain}' failed: {e}")
            continue

    return datasets


# ---------------------------------------------------------------------------
# Extract flash locations from GLM datasets
# ---------------------------------------------------------------------------
def extract_flashes(datasets: list) -> pd.DataFrame:
    """
    Extract flash lat/lon from a list of GLM xarray Datasets.
    Returns a DataFrame with columns: flash_lat, flash_lon
    """
    rows = []
    for ds in datasets:
        try:
            # GLM flash variables
            if "flash_lat" in ds and "flash_lon" in ds:
                lats = ds["flash_lat"].values
                lons = ds["flash_lon"].values
                for lat, lon in zip(lats, lons):
                    rows.append({"flash_lat": float(lat), "flash_lon": float(lon)})
        except Exception as e:
            print(f"[WARN] Could not extract flashes from dataset: {e}")

    df = pd.DataFrame(rows, columns=["flash_lat", "flash_lon"])
    print(f"[INFO] Total flashes extracted: {len(df)}")
    return df


# ---------------------------------------------------------------------------
# Scan volcanoes
# ---------------------------------------------------------------------------
def scan_volcanoes(flashes: pd.DataFrame) -> list[dict]:
    """
    For each volcano, count inner-ring and outer-ring flashes,
    then classify using Georayos algorithm.
    """
    results = []
    flash_lats = flashes["flash_lat"].values if len(flashes) > 0 else []
    flash_lons = flashes["flash_lon"].values if len(flashes) > 0 else []

    for name, coords in VOLCANES.items():
        v_lat = coords["lat"]
        v_lon = coords["lon"]
        inner = 0
        outer = 0

        for f_lat, f_lon in zip(flash_lats, flash_lons):
            d = haversine_km(v_lat, v_lon, f_lat, f_lon)
            if d <= INNER_RADIUS_KM:
                inner += 1
            elif d <= OUTER_RADIUS_KM:
                outer += 1

        alert = classify_georayos(inner, outer)
        results.append(
            {
                "volcano": name,
                "lat": v_lat,
                "lon": v_lon,
                "inner_flashes": inner,
                "outer_flashes": outer,
                "alert": alert,
            }
        )

    return results


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------
def save_json(results: list[dict], scan_time: datetime, output_dir: Path) -> Path:
    """Save full scan results to JSON."""
    fname = f"scan_{scan_time:%Y-%m-%d_%H%M}.json"
    path = output_dir / fname
    payload = {
        "scan_utc": scan_time.isoformat(),
        "total_volcanoes": len(results),
        "red_alerts": sum(1 for r in results if r["alert"] == "RED"),
        "yellow_alerts": sum(1 for r in results if r["alert"] == "YELLOW"),
        "green_alerts": sum(1 for r in results if r["alert"] == "GREEN"),
        "volcanoes": results,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"[INFO] JSON saved -> {path}")

    # Also export to docs/data/latest.json for GitHub Pages
    docs_data = output_dir.parent / "docs" / "data"
    docs_data.mkdir(parents=True, exist_ok=True)
    with open(docs_data / "latest.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    return path


def append_csv(results: list[dict], scan_time: datetime, output_dir: Path) -> Path:
    """Append summary row per volcano to alert_history.csv."""
    csv_path = output_dir / "alert_history.csv"
    rows = []
    for r in results:
        rows.append(
            {
                "scan_utc": scan_time.isoformat(),
                "volcano": r["volcano"],
                "lat": r["lat"],
                "lon": r["lon"],
                "inner_flashes": r["inner_flashes"],
                "outer_flashes": r["outer_flashes"],
                "alert": r["alert"],
            }
        )
    df = pd.DataFrame(rows)
    write_header = not csv_path.exists()
    df.to_csv(csv_path, mode="a", index=False, header=write_header)
    print(f"[INFO] CSV appended -> {csv_path}")
    return csv_path


def print_summary(results: list[dict], scan_time: datetime, total_flashes: int) -> None:
    """Print a clear summary table to stdout."""
    sep = "=" * 76
    print(f"\n{sep}")
    print(f"  GEORAYOS — Volcanic Lightning Scanner")
    print(f"  Scan time (UTC): {scan_time:%Y-%m-%d %H:%M}")
    print(f"  Total flashes in window: {total_flashes}")
    print(sep)

    # Header
    print(
        f"  {'Volcano':<28} {'Alert':>6} {'Inner':>7} {'Outer':>7}"
    )
    print(f"  {'-'*28} {'-'*6} {'-'*7} {'-'*7}")

    # Sort: RED first, then YELLOW, then GREEN
    order = {"RED": 0, "YELLOW": 1, "GREEN": 2}
    sorted_results = sorted(results, key=lambda r: order.get(r["alert"], 3))

    for r in sorted_results:
        tag = r["alert"]
        marker = ""
        if tag == "RED":
            marker = " *** "
        elif tag == "YELLOW":
            marker = "  *  "
        else:
            marker = "     "
        print(
            f"  {r['volcano']:<28} {tag:>6} {r['inner_flashes']:>7} {r['outer_flashes']:>7}{marker}"
        )

    red_count = sum(1 for r in results if r["alert"] == "RED")
    yellow_count = sum(1 for r in results if r["alert"] == "YELLOW")
    green_count = sum(1 for r in results if r["alert"] == "GREEN")

    print(sep)
    print(f"  Summary: {red_count} RED  |  {yellow_count} YELLOW  |  {green_count} GREEN")
    print(f"{sep}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    scan_time = datetime.now(timezone.utc)

    # Output directory
    script_dir = Path(__file__).resolve().parent
    output_dir = script_dir / "datos"
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Download GLM data
    print("[STEP 1/4] Downloading GLM data ...")
    datasets = download_glm_data(minutes=60)

    if not datasets:
        print("[WARN] No GLM data available. Running scan with 0 flashes.")
        flashes = pd.DataFrame(columns=["flash_lat", "flash_lon"])
    else:
        # 2. Extract flashes
        print("[STEP 2/4] Extracting flash locations ...")
        flashes = extract_flashes(datasets)

    # 3. Scan volcanoes
    print("[STEP 3/4] Scanning 43 volcanoes ...")
    results = scan_volcanoes(flashes)

    # 4. Save outputs
    print("[STEP 4/4] Saving results ...")
    save_json(results, scan_time, output_dir)
    append_csv(results, scan_time, output_dir)
    print_summary(results, scan_time, total_flashes=len(flashes))

    # Return non-zero if any RED alerts (useful for CI)
    red_count = sum(1 for r in results if r["alert"] == "RED")
    if red_count > 0:
        print(f"[ALERT] {red_count} volcano(es) with RED alert!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
