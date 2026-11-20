"""Clave `data` del manifiesto: carpeta real de los ficheros del paquete.

Modtopia lee `data` de la raiz de `mod.toml` y, si no existe, usa `assets`:
`m->data = mt_strdup(mt_toml_str(t, "data", "assets"));` (mt_manifest.c:145).
El kit escribe bajo `payload/`, asi que el manifiesto generado tiene que
declararlo. Prueba estructural: ZIP, sin arrancar el juego y sin tocar el dump.
"""

from __future__ import annotations

import os
import tomllib
import zipfile

from pokopia.cli import main
from pokopia.mod import example, load_mod
from pokopia.mod.manifest import LEGACY_MANIFEST, MANIFEST
from pokopia.mod.overlay import Origen
from pokopia.mod.toml_manifest import carpeta_datos, dumps

from tests import helpers

PAQUETE = ".pkmod"


def texto_manifiesto(carpeta: str) -> str:
    with open(os.path.join(carpeta, MANIFEST), "r", encoding="utf-8") as fh:
        return fh.read()


def paquete_de(carpeta: str) -> str:
    salida = [name for name in os.listdir(carpeta) if name.endswith(PAQUETE)]
    assert len(salida) == 1, salida
    return os.path.join(carpeta, salida[0])


def test_example_declara_data_payload_y_sus_ficheros_estan_ahi(tmp_path):
    res = example.escribir(os.path.join(str(tmp_path), "ejemplo"))
    texto = texto_manifiesto(res["dir"])
    doc = tomllib.loads(texto)
    assert 'data = "payload"' in texto
    assert doc["data"] == "payload"
    for entry in doc["romfs"]:
        assert entry["file"].startswith("payload/")
        assert os.path.isfile(os.path.join(res["dir"], entry["file"].replace("/", os.sep)))
    mod = load_mod(res["dir"])
    assert mod.report.ok, [str(i) for i in mod.report.issues]
    assert all(i.code != "schema.unknown_key" for i in mod.report.issues)
    assert mod.doc["data"] == "payload"


def test_pack_del_ejemplo_lleva_data_y_los_ficheros_en_esa_carpeta(tmp_path):
    """Estructura del ZIP: `data` cuadra con las rutas declaradas (sin juego)."""
    destino = str(tmp_path / "ejemplo")
    salida = str(tmp_path / "paquetes")
    assert main(["mod", "example", destino]) == 0
    assert main(["mod", "pack", destino, "-o", salida]) == 0
    with zipfile.ZipFile(paquete_de(salida)) as zf:
        nombres = zf.namelist()
        texto = zf.read(MANIFEST).decode("utf-8")
        doc = tomllib.loads(texto)
        assert 'data = "payload"' in texto
        assert doc["data"] == "payload"
        declarados = {e["file"] for e in doc["romfs"]}
        assert declarados
        assert declarados <= set(nombres)
        # ni un solo fichero fuera de la carpeta declarada, ni uno de mas
        assert set(nombres) == {MANIFEST} | declarados
        assert all(name.startswith(doc["data"] + "/") for name in nombres
                   if name != MANIFEST)
        # la clave sobrevive a tomllib y a una segunda lectura del kit
        mod = Origen(paquete_de(salida)).leer_manifest()
        assert mod.report.ok, [str(i) for i in mod.report.issues]
        assert mod.doc["data"] == "payload"


def test_otra_carpeta_se_declara_con_el_valor_real(tmp_path):
    """Si el autor elige `assets/`, el kit no escribe `payload`. [mt_manifest.c:145]"""
    doc = helpers.mod_romfs_doc("otra-carpeta", [
        {"path": "motor_asset/x.bin", "file": "assets/x.bin", "why": "x"}])
    carpeta = str(tmp_path / "otra-carpeta")
    os.makedirs(os.path.join(carpeta, "assets"), exist_ok=True)
    with open(os.path.join(carpeta, "assets", "x.bin"), "wb") as fh:
        fh.write(b"mis bytes")
    texto = dumps(doc)
    with open(os.path.join(carpeta, MANIFEST), "w", encoding="utf-8") as fh:
        fh.write(texto)
    mod = load_mod(carpeta)
    assert mod.report.ok, [str(i) for i in mod.report.issues]
    assert mod.doc["data"] == "assets"
    assert dumps(mod.doc) == texto                     # idempotente con la clave

    salida = str(tmp_path / "paquetes")
    assert main(["mod", "pack", carpeta, "-o", salida]) == 0
    with zipfile.ZipFile(paquete_de(salida)) as zf:
        assert set(zf.namelist()) == {MANIFEST, "assets/x.bin"}
        empaquetado = tomllib.loads(zf.read(MANIFEST).decode("utf-8"))
        assert empaquetado["data"] == "assets"


def test_data_explicita_sobrevive_y_sin_carpeta_comun_no_se_inventa():
    """La clave del autor se respeta; sin una carpeta comun no se inventa una."""
    doc = helpers.mod_romfs_doc("explicito", [
        {"path": "a.bin", "file": "payload/a.bin", "why": "a"}], data="payload")
    escribto = dumps(doc)
    assert 'data = "payload"' in escribto
    leido = tomllib.loads(escribto)
    assert leido["data"] == "payload"
    assert 'data =' not in dumps(helpers.mod_romfs_doc("sin-carpeta", [
        {"path": "a.bin", "file": "a.bin", "why": "a"}]))
    assert carpeta_datos({"romfs": [{"file": "payload/a.bin"},
                                    {"file": "assets/b.bin"}]}) is None
    assert carpeta_datos({"romfs": []}) is None


def test_validate_acepta_data_y_sigue_rechazando_el_stride_de_f21_c2(tmp_path, capsys):
    plantilla = (
        'id = "con-data"\nversion = "0.1.0"\nname = "Con data"\n'
        'authors = ["tests"]\ngame = ["2.0.1a"]\ntitle = "pokopia"\n'
        'container_md5 = { "LD_C0_R.BIN" = "%s", "LI_C0_R.IDX" = "%s" }\n'
        'contract = "1"\nmod_format = 1\ndata = "payload"\n\n'
        '[[set]]\ntable = 983\nrow = 63\noffset = %d\ntype = "u16"\nvalue = 2998\n'
    )
    for nombre, offset, esperado in (("bueno", 34, 0), ("malo", 67, 1)):
        carpeta = tmp_path / nombre
        carpeta.mkdir()
        (carpeta / MANIFEST).write_text(
            plantilla % ("0" * 32, "1" * 32, offset),
            encoding="utf-8", newline="\n")
        assert main(["mod", "validate", str(carpeta), "--no-container"]) == esperado
        salida = capsys.readouterr().out
        if esperado == 0:
            assert "resultado: OK (0 errores" in salida
        else:
            assert "cruza el stride" in salida
            assert "resultado: INVALIDO" in salida


def test_mod_json_legado_con_data_carga_sin_aviso_de_clave(tmp_path):
    doc = helpers.mod_romfs_doc("legado-data", [
        {"path": "a.bin", "file": "payload/a.bin", "why": "a"}], data="payload")
    ruta = helpers.write_mod(os.path.join(str(tmp_path), "legado"), doc)
    mod = load_mod(os.path.dirname(ruta))
    assert mod.report.ok, [str(i) for i in mod.report.issues]
    assert os.path.basename(mod.manifest) == LEGACY_MANIFEST
    assert all(i.code != "schema.unknown_key" for i in mod.report.issues)
    assert mod.doc["data"] == "payload"
