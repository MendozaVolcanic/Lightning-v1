# Lightning-v1 — Discriminación Rayos/Sismos · Chile Volcánico

## [Dashboard en vivo](https://mendozavolcanic.github.io/Lightning-v1/)

> **https://mendozavolcanic.github.io/Lightning-v1/**

Sistema de monitoreo de rayos volcánicos para **57 volcanes** con **dos fuentes independientes en paralelo**:

- **WWLLN** (red terrestre VLF, global, ventana 1 h)
- **GLM GOES-19** (satélite NOAA, óptico, ventana 15 min, solo hemisferio oeste)

Diseñado para **discriminación operacional rayos/sismos en SERNAGEOMIN**: cuando entra una señal sísmica cerca de un volcán, el dashboard responde si la señal puede ser un rayo (descartable) o un evento real (alta prioridad).

## Volcanes monitoreados (57)

| Zona | # | Volcanes |
|---|---|---|
| **Chile - Norte** | 8 | Taapaca, Parinacota, Guallatiri, Isluga, Irruputuncu, Ollague, San Pedro, Lascar |
| **Chile - Centro** | 9 | Tupungatito, San Jose, Tinguiririca, Planchon-Peteroa, Descabezado Grande, Tatara-San Pedro, Laguna del Maule, Nevado de Longavi, Nevados de Chillan |
| **Chile - Sur** | 13 | Antuco, Copahue, Callaqui, Lonquimay, Llaima, Sollipulli, Villarrica, Quetrupillan, Lanin, Mocho-Choshuenco, Carran - Los Venados, Puyehue - Cordon Caulle, Antillanca - Casablanca |
| **Chile - Austral** | 13 | Osorno, Calbuco, Yate, Hornopiren, Huequi, Michinmahuida, Chaiten, Corcovado, Melimoyu, Mentolat, Cay, Maca, Hudson |
| **Centroamérica (con GLM)** | 7 | Acatenango, Fuego, Agua (GUA) · Concepción, Maderas (NIC) · Orosí, Rincón de la Vieja (CRI) |
| **Mundo (sin GLM, demo)** | 7 | Semeru, Wai Sano, Ranakah (IDN) · Kavachi (SLB) · Ambrym (VUT) · Jingbo (CHN) · Kishb Harrat (SAU) |

Todos están mapeados a IDs GVP (Smithsonian Global Volcanism Program) en `volcanoes.py` — fuente única de verdad.

## Algoritmo Georayos

Cada fuente clasifica independientemente:

| Condición | Alerta de la fuente |
|---|---|
| inner = 0 | 🟢 VERDE |
| inner > 0 AND outer = 0 | 🔴 ROJO |
| inner ≥ 2 × outer | 🔴 ROJO |
| inner > 0 AND inner < 2 × outer | 🟡 AMARILLO |

- **inner**: rayos detectados ≤ 20 km del cráter
- **outer**: rayos detectados entre 20 y 100 km

**Alerta combinada en el dashboard**:
- 🔴 ROJO solo si **ambas fuentes coinciden en ROJO** (alta confianza)
- 🟡 AMARILLO si al menos una fuente reporta ROJO o AMARILLO
- 🟢 VERDE si ambas VERDE (la señal sísmica **no** es eléctrica)

## Uso operacional

1. Entra señal sísmica → abrir dashboard → ubicar volcán en la tabla
2. **VERDE en ambas fuentes** → descartar origen eléctrico
3. **AMARILLO** → posible tormenta regional; ver el mapa para confirmar si los rayos están lejos del cráter
4. **ROJO combinado** → dos sistemas independientes confirman actividad cerca del cráter. Cruzar con cámara y estación sísmica antes de protocolo
5. **Una fuente "caída"** (indicador en barra superior) → confiar en la que está viva

Para post-análisis de un evento (ej. tras un sismo), usar **"Últimas Nh"** en el selector — fusiona múltiples scans históricos para reconstruir la tormenta completa.

## Fuentes de datos

### WWLLN — World Wide Lightning Location Network
- ~80 antenas terrestres VLF, Universidad de Washington
- **Cobertura: global** (incluye todos los volcanes monitoreados)
- Página pública: https://wwlln.net/USGS/Global/
- Latencia: ~1–2 min · Ventana: 1 hora rolling
- Por cada volcán con actividad, descargamos un KML con posiciones individuales (lat, lon, timestamp, residual, # estaciones)

### GLM (GOES-19 Geostationary Lightning Mapper)
- Satélite NOAA en órbita geoestacionaria a 75°W
- **Cobertura: solo hemisferio oeste** (~128°W a 14°W). Cubre todo Chile, Centroamérica, parte de Sudamérica
- Bucket público AWS: `s3://noaa-goes19/GLM-L2-LCFA/`
- Latencia: ~20–60 seg · Ventana: 15 min (45 archivos × 20 seg)
- Por cada flash: lat, lon, timestamp, energía óptica (J), área (m²)

**Por qué dos fuentes**: son físicas distintas (radio VLF vs óptico) y sus sesgos no coinciden. Un flash débil en radio pero brillante ópticamente lo ve GLM y no WWLLN, y al revés. La validación cruzada reduce falsos positivos.

## Arquitectura

```
Lightning-v1/
├── volcanoes.py              ← Fuente única: 57 volcanes (GVP id + coords)
├── wwlln_scraper.py          ← Scrapea tabla HTML WWLLN + KMLs paralelos
├── glm_scraper.py            ← Baja GLM L2 LCFA de AWS S3, filtra haversine
├── merger.py                 ← Fusiona WWLLN + GLM, escribe latest.json + historial
├── requirements.txt          ← Deps pinneadas
├── docs/                     ← Servido por GitHub Pages
│   ├── index.html            ← Dashboard
│   ├── data/
│   │   ├── latest.json       ← Feed combinado (dashboard live)
│   │   ├── wwlln_latest.json ← Feed WWLLN puro
│   │   └── glm_latest.json   ← Feed GLM puro
│   └── datos/
│       ├── index.json        ← Índice de scans históricos
│       └── scan_*.json       ← Historial (14 días de retención)
├── datos/
│   └── alert_history.csv     ← CSV acumulativo permanente (sin posiciones)
├── legacy/
│   └── lightning_scanner.py  ← Prototipo GOES-16 original (no usado)
└── .github/workflows/
    └── lightning.yml         ← Workflow: WWLLN → GLM → merger → commit/push
```

## Pipeline

```
       ┌──────────────────────┐         ┌─────────────────────┐
       │ wwlln_scraper.py     │         │ glm_scraper.py      │
       │ (tabla + KMLs)       │         │ (S3 NetCDF parallel)│
       └──────────┬───────────┘         └──────────┬──────────┘
                  │                                │
       wwlln_latest.json                 glm_latest.json
                  │                                │
                  └──────────────┬─────────────────┘
                                 ▼
                        ┌──────────────────┐
                        │ merger.py        │
                        │ - dedup posiciones│
                        │ - alerta combinada│
                        │ - historial       │
                        │ - índice          │
                        └────────┬─────────┘
                                 ▼
                ┌────────────────┴───────────────┐
                │                                │
        docs/data/latest.json          docs/datos/scan_*.json
                │                                │
                ▼                                ▼
          Dashboard live              Selector histórico
```

## Dashboard

- Mapa Leaflet con marcadores RGB por volcán (alerta combinada)
- Click en volcán → anillos 20 km / 100 km + ⚡ posiciones individuales
- ⚡ **rojo/dorado** = WWLLN inner/outer · ⚡ **magenta/cyan** = GLM inner/outer
- Toggles por fuente (`⚡ WWLLN` / `⚡ GLM`) — ocultar visualmente uno u otro
- **3 modos de visualización:**
  - **LIVE**: scan más reciente, auto-refresh 60 s sin recargar la página
  - **Últimas 30m/1h/3h/6h/12h/24h**: fusiona N scans, unifica ventanas, deduplica
  - **Histórico**: snapshot único de un momento pasado
- Modal de ayuda (botón ⓘ) con metodología completa
- Hora local del navegador junto a UTC
- Indicador de antigüedad del dato (verde < 20 min, naranja > 20 min)

## Cadencia

- **5 min** disparado por **cron externo** (cron-job.org → `workflow_dispatch` API de GitHub)
- El cron nativo de GitHub Actions (`schedule:`) está como fallback pero suele tener gaps de 1–2 h por throttling en horas pico
- Cada run típico: ~1m13s (instalación + scrape + merge + commit + push)

Para cambiar la cadencia: editar la expresión `*/5 * * * *` en cron-job.org (no requiere cambios en código).

## Ejecución local

```bash
pip install -r requirements.txt
python wwlln_scraper.py   # genera docs/data/wwlln_latest.json
python glm_scraper.py     # genera docs/data/glm_latest.json
python merger.py          # genera docs/data/latest.json + scan histórico
```

Para servir el dashboard local:
```bash
python -m http.server -d docs 8000
# Abrir http://localhost:8000/
```

## Esquema de `latest.json`

```jsonc
{
  "scan_utc": "2026-04-30T15:43:58+00:00",
  "total_volcanoes": 57,
  "red_alerts": 0,
  "yellow_alerts": 1,
  "green_alerts": 56,
  "sources": {
    "wwlln": { "available": true, "scan_utc": "...", "window_hours": 1 },
    "glm":   { "available": true, "scan_utc": "...", "window_minutes": 15 }
  },
  "volcanoes": [
    {
      "volcano": "Kavachi (SLB)",
      "wwlln_id": "0505-06-",
      "lat": -9.02, "lon": 157.95,
      "alert": "YELLOW",
      "sources": {
        "wwlln": {
          "available": true, "inner": 5, "outer": 124, "alert": "YELLOW",
          "positions": [{"lat":-9.02,"lon":157.95,"ring":"inner","time":"...","residual_us":4.2,"stations":7}, ...]
        },
        "glm": {
          "available": true, "inner": 0, "outer": 0, "alert": "GREEN",
          "positions": []
        }
      }
    }
  ]
}
```

## Antecedentes científicos

- **Puyehue-Cordón Caulle 2011**: WWLLN detectó actividad eléctrica 30 min antes que OVDAS
- **Calbuco 2015**: 1 016 rayos registrados durante la erupción (Van Eaton et al. 2016)
- Los rayos volcánicos son la primera señal detectable de erupción explosiva por propagación EM

## Roadmap

- [ ] Agregar Himawari LMI (cobertura Pacífico) para Indonesia/Vanuatu/China
- [ ] Agregar MTG-I1 LI (cobertura Europa/África) para Arabia
- [ ] Notificaciones automáticas a SERNAGEOMIN cuando alerta combinada ROJA
- [ ] Smoke tests con mock de WWLLN y GLM
- [ ] Rotación mensual del CSV histórico

## Licencia

Sin licencia formal aún. Uso interno SERNAGEOMIN.

## Contacto

Nicolás Mendoza — geólogo SERNAGEOMIN
