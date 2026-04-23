# Lightning-v1 — Discriminación Rayos/Sismos · Chile Volcánico

## [Dashboard en vivo](https://mendozavolcanic.github.io/Lightning-v1/)

> **https://mendozavolcanic.github.io/Lightning-v1/**

Sistema de monitoreo de rayos volcánicos para **43 volcanes chilenos**, basado en datos WWLLN (World Wide Lightning Location Network). Diseñado para discriminación operacional de señales sísmicas en SERNAGEOMIN.

## Uso operacional

Cuando se detecta una señal sísmica en una estación cercana a un volcán:

1. Abrir el dashboard → verificar estado del volcán
2. **VERDE** → sin rayos en ≤20 km → la señal sísmica **no es de origen eléctrico**
3. **AMARILLO** → tormenta eléctrica regional → puede haber interferencia
4. **ROJO** → rayos concentrados cerca del cráter → confirmar origen antes de activar protocolo sísmico

## Algoritmo Georayos

| Condición | Alerta |
|-----------|--------|
| inner = 0 | 🟢 VERDE |
| inner > 0 AND outer = 0 | 🔴 ROJO |
| inner ≥ 2 × outer | 🔴 ROJO |
| inner > 0 AND inner < 2 × outer | 🟡 AMARILLO |

- **inner**: rayos detectados ≤ 20 km del cráter
- **outer**: rayos detectados entre 20 y 100 km

## Fuente de datos

**WWLLN** — World Wide Lightning Location Network  
Universidad de Washington · https://wwlln.net  

- Latencia de detección: ~1–2 minutos
- Página USGS/GVP: https://wwlln.net/USGS/Global/
- Cada volcán tiene un archivo KML con posiciones individuales de rayos
- Los conteos de la tabla HTML se actualizan en tiempo casi real

## Dashboard

**GitHub Pages**: `https://<usuario>.github.io/Lightning-v1/`

Funcionalidades:
- Mapa interactivo con marcadores RED/YELLOW/GREEN
- Click en volcán → anillos de 20 km y 100 km visibles en el mapa
- Marcadores ⚡ para posiciones individuales de rayos (cuando hay actividad)
- Auto-refresh cada 5 minutos
- Indicador de antigüedad del dato (verde < 20 min, naranja > 20 min)

## Ejecución local

```bash
pip install -r requirements.txt
python wwlln_scraper.py
```

Salidas:
- `docs/data/latest.json` — datos para el dashboard
- `datos/scan_YYYY-MM-DD_HHMM.json` — archivo histórico

## Automatización GitHub Actions

El workflow corre cada **10 minutos** y hace push del `latest.json` actualizado.

```yaml
schedule:
  - cron: '*/10 * * * *'
```

Para activar GitHub Pages: Settings → Pages → Source: `main / docs`

## Volcanes monitoreados (43)

| Zona | Volcanes |
|------|----------|
| Norte | Taapaca, Parinacota, Guallatiri, Isluga, Irruputuncu, Ollague, San Pedro, Lascar |
| Centro | Tupungatito, San Jose, Tinguiririca, Planchon-Peteroa, Descabezado Grande, Tatara-San Pedro, Laguna del Maule, Nevado de Longavi, Nevados de Chillan |
| Sur | Antuco, Copahue, Callaqui, Lonquimay, Llaima, Sollipulli, Villarrica, Quetrupillan, Lanin, Mocho-Choshuenco, Carran-Los Venados, Puyehue-CC, Antillanca |
| Austral | Osorno, Calbuco, Yate, Hornopiren, Huequi, Michinmahuida, Chaiten, Corcovado, Melimoyu, Mentolat, Cay, Maca, Hudson |

Todos mapeados a IDs GVP (1505-xxx, 1507-xxx, 1508-xxx) en WWLLN.

## Arquitectura

```
Lightning-v1/
├── wwlln_scraper.py          — Scraper WWLLN + Georayos + KML parser
├── docs/
│   ├── index.html            — Dashboard (GitHub Pages)
│   └── data/
│       └── latest.json       — Último escaneo
├── datos/
│   └── scan_*.json           — Historial
├── requirements.txt          — requests, beautifulsoup4
└── .github/workflows/
    └── lightning.yml         — Ejecución cada 10 min
```

## Antecedentes

- Puyehue-Cordón Caulle 2011: WWLLN detectó actividad eléctrica 30 min antes que OVDAS
- Calbuco 2015: 1,016 rayos registrados durante la erupción
- Los rayos son la primera señal detectable de erupción explosiva (propagación EM)
