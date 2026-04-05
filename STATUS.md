# STATUS — Lightning-v1

## Estado actual
Proyecto nuevo — en fase de planificacion e investigacion.

## Objetivo
Deteccion automatizada de rayos volcanicos para 43 volcanes chilenos usando GOES-16 GLM.
Basado en el algoritmo Georayos-VolcanoAr (Burgos et al., 2021).

## Ultimos cambios
- 2026-04-05: Creacion del proyecto, literatura recopilada

## Problemas conocidos
- GOES GLM es optico, puede perder detecciones con ceniza densa
- Necesita filtro para rayos meteorologicos (tormentas no volcanicas)

## Proximo paso
- Implementar descarga GLM via goes2go
- Configurar anillos de 20km/100km para 43 volcanes
- Probar con datos historicos de Calbuco 2015

## Archivos clave
- `docs/literatura_lightning.md` — revision de literatura
- `PLAN.md` — plan de proyecto y arquitectura
