#!/usr/bin/env python3
"""
merger.py — Combina feeds WWLLN + GLM en el JSON que consume el dashboard
=========================================================================
Lee:
  docs/data/wwlln_latest.json  (escrito por wwlln_scraper.py)
  docs/data/glm_latest.json    (escrito por glm_scraper.py)

Escribe:
  docs/data/latest.json                      — feed combinado (live)
  docs/datos/scan_YYYY-MM-DD_HHMM.json       — scan combinado histórico
  docs/datos/index.json                      — índice de scans disponibles

Lógica de alerta combinada:
  RED      — ambas fuentes reportan RED (confirmado)
  YELLOW   — al menos una fuente RED o YELLOW
  GREEN    — ambas fuentes GREEN o fuente ausente

Si una fuente falta o falla, el dashboard sigue mostrando la otra.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from volcanoes import VOLCANOES

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
RETENTION_DAYS = 30


# ---------------------------------------------------------------------------
# Lógica de combinación
# ---------------------------------------------------------------------------
def combined_alert(w_alert: str | None, g_alert: str | None) -> str:
    """
    RED      : las dos fuentes RED
    YELLOW   : una fuente RED o YELLOW (o ambas YELLOW)
    GREEN    : ambas GREEN o una ausente y la otra GREEN
    """
    both_red = w_alert == "RED" and g_alert == "RED"
    any_red_or_yellow = any(a in ("RED", "YELLOW") for a in (w_alert, g_alert) if a)
    if both_red:
        return "RED"
    if any_red_or_yellow:
        return "YELLOW"
    return "GREEN"


def _load_feed(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[WARN] lectura {path.name}: {exc}")
        return None


def _index_by_name(payload: dict | None) -> dict[str, dict]:
    if not payload:
        return {}
    return {v["volcano"]: v for v in payload.get("volcanoes", [])}


# ---------------------------------------------------------------------------
# Construcción del payload combinado
# ---------------------------------------------------------------------------
def build_combined(
    wwlln: dict | None,
    glm: dict | None,
    scan_time: datetime,
) -> dict:
    w_by_name = _index_by_name(wwlln)
    g_by_name = _index_by_name(glm)

    volcanoes_out: list[dict] = []
    for name, (wwlln_id, vlat, vlon) in VOLCANOES.items():
        w = w_by_name.get(name, {})
        g = g_by_name.get(name, {})

        w_alert = w.get("alert")
        g_alert = g.get("alert")
        alert   = combined_alert(w_alert, g_alert)

        volcanoes_out.append({
            "volcano":  name,
            "wwlln_id": wwlln_id,
            "lat":      w.get("lat", vlat),
            "lon":      w.get("lon", vlon),
            "alert":    alert,
            "sources": {
                "wwlln": {
                    "available": bool(w),
                    "inner":     w.get("inner_strokes", 0),
                    "outer":     w.get("outer_strokes", 0),
                    "alert":     w_alert or "UNKNOWN",
                    "positions": w.get("stroke_positions", []),
                },
                "glm": {
                    "available": bool(g),
                    "inner":     g.get("inner_flashes", 0),
                    "outer":     g.get("outer_flashes", 0),
                    "alert":     g_alert or "UNKNOWN",
                    "positions": g.get("flash_positions", []),
                },
            },
        })

    red    = sum(1 for v in volcanoes_out if v["alert"] == "RED")
    yellow = sum(1 for v in volcanoes_out if v["alert"] == "YELLOW")
    green  = sum(1 for v in volcanoes_out if v["alert"] == "GREEN")

    return {
        "scan_utc":        scan_time.isoformat(),
        "total_volcanoes": len(volcanoes_out),
        "red_alerts":      red,
        "yellow_alerts":   yellow,
        "green_alerts":    green,
        "sources": {
            "wwlln": {
                "available":    wwlln is not None,
                "scan_utc":     (wwlln or {}).get("scan_utc"),
                "window_hours": (wwlln or {}).get("window_hours"),
                "error":        (wwlln or {}).get("error"),
            },
            "glm": {
                "available":      glm is not None,
                "scan_utc":       (glm or {}).get("scan_utc"),
                "window_minutes": (glm or {}).get("window_minutes"),
                "error":          (glm or {}).get("error"),
            },
        },
        "volcanoes": volcanoes_out,
    }


# ---------------------------------------------------------------------------
# Histórico e índice
# ---------------------------------------------------------------------------
def _write_history(combined: dict, scan_time: datetime, script_dir: Path) -> Path:
    docs_datos = script_dir / "docs" / "datos"
    docs_datos.mkdir(parents=True, exist_ok=True)
    fname = f"scan_{scan_time:%Y-%m-%d_%H%M}.json"
    with open(docs_datos / fname, "w", encoding="utf-8") as f:
        json.dump(combined, f, indent=2, ensure_ascii=False)
    print(f"[INFO] scan histórico → docs/datos/{fname}")
    return docs_datos


def _update_index(
    docs_datos: Path, new_fname: str, scan_time: datetime, red: int, yellow: int
) -> None:
    index_path = docs_datos / "index.json"
    if index_path.exists():
        try:
            idx = json.loads(index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            idx = {"scans": []}
    else:
        idx = {"scans": []}

    existing = {s["file"] for s in idx.get("scans", [])}
    if new_fname not in existing:
        idx.setdefault("scans", []).append({
            "file":     new_fname,
            "scan_utc": scan_time.isoformat(),
            "red":      red,
            "yellow":   yellow,
        })

    idx["scans"].sort(key=lambda s: s["scan_utc"], reverse=True)

    cutoff = (scan_time - timedelta(days=RETENTION_DAYS)).isoformat()
    idx["scans"] = [s for s in idx["scans"] if s["scan_utc"] >= cutoff]
    idx["updated"] = scan_time.isoformat()

    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(idx, f, indent=2, ensure_ascii=False)
    print(f"[INFO] index.json → docs/datos/index.json ({len(idx['scans'])} scans)")


def _purge_old_scans(docs_datos: Path, now: datetime) -> None:
    cutoff = now - timedelta(days=RETENTION_DAYS)
    deleted = 0
    for f in sorted(docs_datos.glob("scan_*.json")):
        try:
            date_str = f.stem[len("scan_"):]
            dt = datetime.strptime(date_str, "%Y-%m-%d_%H%M").replace(tzinfo=timezone.utc)
            if dt < cutoff:
                f.unlink()
                deleted += 1
        except ValueError:
            pass
    if deleted:
        print(f"[INFO] Purgados {deleted} scan(s) > {RETENTION_DAYS} días")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    script_dir = Path(__file__).resolve().parent
    docs_data  = script_dir / "docs" / "data"

    wwlln = _load_feed(docs_data / "wwlln_latest.json")
    glm   = _load_feed(docs_data / "glm_latest.json")

    if not wwlln and not glm:
        print("[ERROR] Ninguna fuente disponible — abortando merge")
        return 1

    scan_time = datetime.now(timezone.utc)
    combined  = build_combined(wwlln, glm, scan_time)

    # 1. latest.json (dashboard live)
    docs_data.mkdir(parents=True, exist_ok=True)
    with open(docs_data / "latest.json", "w", encoding="utf-8") as f:
        json.dump(combined, f, indent=2, ensure_ascii=False)
    print(f"[INFO] latest.json → {docs_data / 'latest.json'}")

    # 2. Histórico combinado + índice
    docs_datos = _write_history(combined, scan_time, script_dir)
    fname = f"scan_{scan_time:%Y-%m-%d_%H%M}.json"
    _update_index(
        docs_datos, fname, scan_time,
        combined["red_alerts"], combined["yellow_alerts"],
    )

    # 3. Purga > 30 días
    _purge_old_scans(docs_datos, scan_time)

    # Resumen
    sep = "=" * 72
    print(f"\n{sep}")
    print(f"  MERGE COMBINADO  |  {scan_time:%Y-%m-%d %H:%M} UTC")
    print(f"  WWLLN: {'OK' if wwlln else 'NO DISPONIBLE'}  |  GLM: {'OK' if glm else 'NO DISPONIBLE'}")
    print(f"  Alertas finales: R={combined['red_alerts']}  Y={combined['yellow_alerts']}  G={combined['green_alerts']}")
    print(sep + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
