# Literatura: Deteccion de Rayos Volcanicos para Monitoreo

## Fuentes de Datos Disponibles

### 1. GOES-16 GLM (Geostationary Lightning Mapper) — RECOMENDADO PRINCIPAL
- Cobertura: 52°N a 52°S — cubre TODO Chile
- Latencia: ~20 segundos
- Costo: GRATIS via AWS (NOAA Open Data)
- Formato: NetCDF (GLM-L2-LCFA)
- Python: `goes2go` (conda install -c conda-forge goes2go)
- Python avanzado: `glmtools` (github.com/deeplycloudy/glmtools)
- Detecta: IC + CC + CG (total lightning, sensor optico NIR)
- Limitacion: sensor optico, puede ser bloqueado por ceniza/nube densa

### 2. WWLLN (World Wide Lightning Location Network)
- ~70 sensores VLF globales, University of Washington
- Latencia: ~1 minuto
- Costo: Suscripcion (contactar Prof. Robert Holzworth, bobholz@washington.edu)
- Formato: CSV ASCII (ano/mes/dia, hora:min:seg, lat, lon, residual, nsta)
- Eficiencia: ~30% global (CG >30kA), 60% para >50kA
- Tiene Ash Cloud Monitor (ACM) especifico para volcanes
- Archivos desde 2004

### 3. Vaisala GLD360
- Latencia: 35 segundos
- Costo: Comercial (contactar Vaisala)
- Python: satpy reader (`satpy.readers.vaisala_gld360`)
- Precision: 1 km mediana
- Tiene algoritmo patentado para deteccion de ceniza volcanica

### 4. Earth Networks ENTLN
- 1,800+ sensores, 100+ paises
- Costo: Comercial
- Python: github.com/engelsjk/python-lightning-earthnetworks (TCP socket + JSON)

### 5. Blitzortung
- Red comunitaria, gratuita
- No validado para uso volcanico

## Papers Criticos

### Van Eaton et al. (2016) — Calbuco, Chile
- WWLLN detecto 93 rayos (Fase 1) y 1,016 rayos (Fase 2)
- 30-37 minutos de delay entre inicio de erupcion y deteccion de rayos
- Los cambios en actividad electrica correlacionan con tasa de erupcion
- DOI: 10.1002/2016gl068076

### Burgos et al. (2021) — Georayos-VolcanoAr
- Sistema argentino sobre WWLLN para 32 volcanes andinos
- Algoritmo Red/Yellow/Green con anillos de 20km y 100km
- Redujo falsos positivos en 75% vs ACM crudo
- DOI: 10.1016/j.jsames.2021.103234

### Nicora et al. (2013) — Puyehue-Cordon Caulle
- WWLLN ACM alerto 30 minutos ANTES que SERNAGEOMIN/OVDAS
- Correlacion espacial entre rayos y pluma volcanica

### Behnke (2022) — Clasificacion VHF
- Regresion logistica: 97.9% precision clasificando descargas volcanicas vs rayos
- DOI: 10.1029/2022GL099370

### Vossen et al. — Sakurajima observacion a largo plazo
- Sensor Biral BTD-200 detecto actividad electrica en 511/724 explosiones (71%)
- Redes globales solo detectaron 1-2 de los mismos 724 eventos

## Contactos Clave
- Prof. Robert Holzworth (UW, WWLLN): bobholz@washington.edu
- Gabriela Nicora (CONICET, Georayos-VolcanoAr)
- Alexa Van Eaton (USGS, volcanic lightning research)

## Repos GitHub Disponibles
| Repo | Proposito |
|------|-----------|
| goes2go | Descarga GOES GLM de AWS |
| glmtools | Procesamiento avanzado GLM NetCDF |
| lmatools | Lightning Mapping Array |
| python-lightning-earthnetworks | TCP ENTLN |
| WGLC | WWLLN Global Lightning Climatology |

## Items NO encontrados
- API publica de WWLLN (no existe, solo suscripcion/email)
- Acceso publico a Georayos-VolcanoAr (herramienta interna CONICET)
- Sistema open-source completo de alertas volcanicas por rayos en GitHub (no existe)
- Precios especificos de WWLLN y GLD360
