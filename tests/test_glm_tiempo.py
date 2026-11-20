"""
Hora de cada destello GLM.

En GLM-L2-LCFA los desfases de tiempo (flash_time_offset_of_first_event y sus
pares de evento y grupo) se guardan como int16 empaquetado: `_Unsigned = true`,
`scale_factor` ~0,00038 s, `add_offset` -5 s y `units` = "seconds since <inicio
del gránulo>". El valor físico es (uint16 * scale_factor + add_offset) segundos
desde ese origen, entre -5 y +20 s. Hasta nov-2026 el scraper sumaba el entero
crudo con signo como si fueran segundos, y la hora quedaba corrida hasta ~9 h.

La prueba sin red arma un archivo con esa misma estructura. La prueba contra
S3 baja un gránulo real de noaa-goes19 y corre sólo con GLM_S3_TEST=1.
"""

import io
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import glm_scraper

INICIO = datetime(2026, 11, 20, 11, 19, 40, tzinfo=timezone.utc)
FIN = INICIO + timedelta(seconds=20)
# Empaque de los archivos reales de GOES-19 (leído de un gránulo del 20-11-2026).
SCALE_T = 0.00038147560553625226
OFFSET_T = -5.0
UMBRAL_DESTELLO_S = 3.33   # flash_time_threshold de LCFA


class _Resp:
    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self):
        pass


class _SesionFalsa:
    """Imita requests.Session.get devolviendo bytes ya armados."""

    def __init__(self, content: bytes):
        self._content = content

    def get(self, url, timeout=None):
        return _Resp(self._content)


def _granulo_sintetico(path: Path, desfases_s: list[float]) -> None:
    import h5netcdf.legacyapi as nc

    crudo_t = np.round((np.array(desfases_s) - OFFSET_T) / SCALE_T).astype(np.uint16)
    n = len(desfases_s)
    with nc.Dataset(path, "w") as ds:
        ds.time_coverage_start = INICIO.strftime("%Y-%m-%dT%H:%M:%S.0Z")
        ds.time_coverage_end = FIN.strftime("%Y-%m-%dT%H:%M:%S.0Z")
        ds.createDimension("number_of_flashes", n)

        pt = ds.createVariable("product_time", "f8", ())
        pt.units = "seconds since 2000-01-01 12:00:00"
        pt[...] = (INICIO - datetime(2000, 1, 1, 12, tzinfo=timezone.utc)).total_seconds()

        for nombre, valor in (("flash_lat", -36.868), ("flash_lon", -71.378)):
            v = ds.createVariable(nombre, "f4", ("number_of_flashes",))
            v[:] = np.full(n, valor, dtype=np.float32)

        for nombre in ("flash_time_offset_of_first_event", "flash_time_offset_of_last_event"):
            v = ds.createVariable(nombre, "i2", ("number_of_flashes",))
            v.scale_factor = np.float32(SCALE_T)
            v.add_offset = np.float32(OFFSET_T)
            v._Unsigned = "true"
            v.units = "seconds since " + INICIO.strftime("%Y-%m-%d %H:%M:%S.000")
            v[:] = crudo_t.view(np.int16)

        # Energía empaquetada igual (uint16 con escala); un crudo >= 32768 se
        # lee negativo si se ignora _Unsigned.
        e = ds.createVariable("flash_energy", "i2", ("number_of_flashes",), fill_value=np.int16(-1))
        e.scale_factor = np.float32(9.999959802209943e-16)
        e.add_offset = np.float32(2.8514998886357517e-16)
        e._Unsigned = "true"
        e.units = "J"
        e[:] = np.full(n, 40000, dtype=np.uint16).view(np.int16)


def test_hora_del_destello_dentro_del_granulo(tmp_path):
    # -1,5 s: destello que empezó antes del inicio nominal (pasa en archivos
    # reales). 15 s: su entero crudo es >= 32768, negativo leído como int16.
    desfases = [-1.5, 0.0, 7.0, 15.0, 19.9]
    f = tmp_path / "glm.nc"
    _granulo_sintetico(f, desfases)

    flashes = glm_scraper._download_and_parse(_SesionFalsa(f.read_bytes()), "OR_GLM_sintetico.nc")

    assert len(flashes) == len(desfases)
    for fl, esperado in zip(flashes, desfases):
        t = datetime.fromisoformat(fl["time"])
        assert INICIO - timedelta(seconds=UMBRAL_DESTELLO_S) <= t <= FIN, fl["time"]
        # El rótulo se guarda con resolución de segundo (truncado).
        assert abs((t - INICIO).total_seconds() - esperado) <= 1.0, (fl["time"], esperado)


def test_energia_no_negativa(tmp_path):
    f = tmp_path / "glm.nc"
    _granulo_sintetico(f, [0.0, 10.0])
    flashes = glm_scraper._download_and_parse(_SesionFalsa(f.read_bytes()), "OR_GLM_sintetico.nc")
    for fl in flashes:
        assert fl["energy_j"] is not None and fl["energy_j"] > 0, fl


@pytest.mark.skipif(os.environ.get("GLM_S3_TEST") != "1", reason="red: correr con GLM_S3_TEST=1")
def test_granulo_real_de_s3():
    """Cada destello de un archivo real cae entre el inicio (menos el umbral de
    duración de destello del propio archivo) y el fin del gránulo."""
    import xarray as xr

    host = glm_scraper.S3_HOST
    ahora = datetime.now(timezone.utc) - timedelta(hours=1)
    prefijo = f"{glm_scraper.S3_PRODUCT}/{ahora.year}/{ahora.timetuple().tm_yday:03d}/{ahora.hour:02d}/"
    import requests
    sesion = requests.Session()
    keys = glm_scraper._list_hour(sesion, ahora)
    assert keys, f"sin archivos en {prefijo}"
    key = keys[len(keys) // 2]

    contenido = urllib.request.urlopen(f"{host}/{key}", timeout=60).read()
    ds = xr.open_dataset(io.BytesIO(contenido), engine="h5netcdf")
    inicio = datetime.fromisoformat(ds.attrs["time_coverage_start"].replace("Z", "+00:00"))
    fin = datetime.fromisoformat(ds.attrs["time_coverage_end"].replace("Z", "+00:00"))
    umbral = float(ds["flash_time_threshold"].values)
    ds.close()

    flashes = glm_scraper._download_and_parse(_SesionFalsa(contenido), key)
    assert flashes, f"{key} sin destellos"
    fuera = [fl["time"] for fl in flashes
             if not (inicio - timedelta(seconds=umbral) - timedelta(seconds=1)
                     <= datetime.fromisoformat(fl["time"]) <= fin)]
    assert not fuera, f"{key}: {len(fuera)} de {len(flashes)} fuera de [{inicio}, {fin}]: {fuera[:5]}"
