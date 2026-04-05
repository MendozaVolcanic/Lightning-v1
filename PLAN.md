# Lightning-v1 — Plan de Proyecto

## Objetivo
Sistema automatizado de deteccion de rayos volcanicos para 43 volcanes chilenos, usando datos GOES-16 GLM (gratuitos) como fuente principal.

## Por que importa
- Los rayos son la PRIMERA senal detectable de una erupcion explosiva
- Mas rapido que sismica o infrasonica (propagacion electromagnetica)
- WWLLN alerto 30 min antes que OVDAS en Puyehue-CC 2011
- WWLLN detecto 1,016 rayos en Calbuco 2015

## Arquitectura
```
GOES-16 GLM (AWS, cada ~5 min)
    |
    v
Lightning-v1/
├── config_volcanes.py        — 43 volcanes + anillos 20km/100km
├── glm_downloader.py         — Descarga GLM L2 de AWS via goes2go
├── lightning_detector.py     — Filtra rayos dentro de anillos volcanicos
├── alert_classifier.py       — Clasificacion Red/Yellow/Green (Georayos)
├── alert_generator.py        — Genera alertas markdown
├── visualizador.py           — Mapa de rayos + volcanes
├── docs/index.html           — Dashboard GitHub Pages
└── .github/workflows/
    └── lightning.yml         — Workflow cada 5-10 minutos
```

## Algoritmo (basado en Georayos-VolcanoAr)
```
Para cada volcan:
  Anillo interior: 20 km del crater
  Anillo exterior: 20-100 km del crater

  Cada X minutos:
    Descargar ultimos datos GLM
    Contar rayos en anillo interior (N_inner)
    Contar rayos en anillo exterior (N_outer)

    Si N_inner > 0 AND N_outer == 0:
      ALERTA ROJA (solo rayos cerca del volcan)
    Si N_inner > 0 AND N_inner >= 2 * N_outer:
      ALERTA ROJA (concentracion volcanica)
    Si N_inner > 0 AND N_inner < 2 * N_outer:
      ALERTA AMARILLA (senal mixta)
    Si N_inner == 0:
      VERDE (sin actividad)
```

## Fases

### Fase 1: MVP con GOES GLM (1 semana)
1. Configurar descarga automatica de GOES-16 GLM via goes2go
2. Implementar filtro geoespacial (rayos dentro de 20km/100km de cada volcan)
3. Clasificacion Red/Yellow/Green
4. Dashboard con mapa de alertas

### Fase 2: Refinamiento (semana 2)
5. Historico de alertas (timeline por volcan)
6. Filtro de tormentas electricas (descartar rayos meteorologicos)
7. Persistencia temporal (requiere N rayos en ventana de T minutos)

### Fase 3: Integracion (semana 3)
8. Cross-reference con datos VRP termicos
9. Notificacion Telegram cuando alerta roja
10. Integracion con dashboard unificado

## Datos GOES GLM
```python
from goes2go import GOES
G = GOES(satellite=16, product="GLM-L2-LCFA", domain='C')
ds = G.nearesttime('2026-04-05')
# Campos: event_lat, event_lon, event_energy, flash_lat, flash_lon, etc.
```

## Dashboard
- Repo GitHub con GitHub Pages
- Mapa interactivo de volcanes + rayos recientes
- Timeline de alertas por volcan
- Tabla resumen Red/Yellow/Green de los 43 volcanes

## Dependencias
- goes2go (descarga GOES)
- xarray (lectura NetCDF)
- numpy, scipy (analisis geoespacial)
- folium o leaflet.js (mapa interactivo)
- matplotlib (graficos)
