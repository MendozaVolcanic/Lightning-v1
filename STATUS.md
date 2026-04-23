# STATUS — Lightning-v1

## Estado actual (2026-04-23)

Operativo con fuente WWLLN. Dashboard listo. GitHub Pages pendiente de activar.

## Fuente de datos

**WWLLN** — https://wwlln.net/USGS/Global/  
Latencia: ~1–2 min · Actualización página: tiempo casi real  
GitHub Actions: cada 10 minutos

## Completado

- `wwlln_scraper.py` — scrape tabla HTML + KMLs paralelos + Georayos + JSON
  - 1 request HTTP para todos los volcanes (tabla completa)
  - KMLs descargados en paralelo solo para volcanes con rayos activos
  - Tiempo típico: <5s sin rayos, <15s con tormenta activa
- `docs/index.html` — dashboard actualizado
  - Anillos 20km y 100km al hacer click en volcán
  - Marcadores ⚡ individuales desde KML cuando hay actividad
  - Indicador de antigüedad del dato
  - Auto-refresh 5 min
  - Discriminación operacional sismos/rayos en metodología
- `.github/workflows/lightning.yml` — cron cada 10 min, usa wwlln_scraper.py
- `requirements.txt` — reducido a requests + beautifulsoup4 (sin goes2go/xarray)
- `README.md` — documentación con contexto operacional SERNAGEOMIN

## Pendiente

- **GitHub Pages**: activar en Settings → Pages → main/docs
- Verificar update frequency exacta de WWLLN con datos reales en producción

## Arquitectura

```
docs/data/latest.json   ← wwlln_scraper.py → GitHub Pages
docs/index.html         ← dashboard
```

## Notas técnicas

- inner = strokes <20km (columna 6 de tabla WWLLN)
- outer = strokes <100km (col 7) minus inner → anillo 20-100km
- KML namespace: http://www.opengis.net/kml/2.2
- Volcanes mapeados: 43/43 con ID GVP (1505, 1507, 1508)
- `lightning_scanner.py` (GOES-16) se mantiene como fallback alternativo
