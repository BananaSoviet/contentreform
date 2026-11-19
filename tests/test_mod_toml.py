"""Puente del manifiesto (D-028, camino b): `mod.toml` nativo, `mod.json` legado.

Un test por criterio de aceptacion de M0 (`docs/PLAN-1.0.md`):

1. `pkp mod new` escribe un `mod.toml` con `id`, `version` y `game`, y nada
   inventado;
2. `pkp mod validate` lo acepta, exit 0;
3. un paquete viejo con `mod.json` sigue cargando igual — carpeta y `.pkmod`;
4. los tests de `tests/test_mod_*.py` siguen verdes (los de formato se
   adaptan al nuevo, no al reves: se cuentan en la suite).

Y lo que el puente no puede romper: que las dos formas carguen lo mismo, que el
`id` valga para Modtopia, que la seccion de celdas de F19 quepa en el mismo
fichero sin que el kit la rechace, y que escribir y leer sea idempotente.
"""

from __future__ import annotations

import json
import os
import tomllib
import zipfile

import pytest

from pokopia.cli import main
from pokopia.mod import load_mod, validate
from pokopia.mod.errors import ModError
from pokopia.mod.manifest import LEGACY_MANIFEST, MANIFEST
from pokopia.mod.overlay import Origen
from pokopia.mod.toml_manifest import dumps, id_problema

from tests import helpers

#: Claves que `pkp mod new` puede escribir. Ninguna es nueva: todas existian en
#: `mod.json` o son las que Modtopia pide en su `mod.toml`.
CLAVES_DE_NEW = {"id", "version", "name", "authors", "description", "game",
                 "mod_format", "title", "container_md5"}


def _new(tmp_path, nombre="mi-mod"):
    """`pkp mod new` en una carpeta limpia; devuelve la carpeta."""
    with helpers.records_spec():
        cont = helpers.make_container(str(tmp_path / "c"), {1: b"x" * 10})
        destino = str(tmp_path / nombre)
        assert main(["mod", "new", nombre, "--dir", destino,
                     "--container", cont.dir]) == 0
    return destino


# --------------------------------------------------------------------------
# 1 y 2: lo que escribe y lo que acepta
# --------------------------------------------------------------------------

def test_1_new_escribe_mod_toml_con_id_version_y_game(tmp_path):
    destino = _new(tmp_path)
    assert os.path.isfile(os.path.join(destino, MANIFEST))
    assert not os.path.exists(os.path.join(destino, LEGACY_MANIFEST))
    with open(os.path.join(destino, MANIFEST), encoding="utf-8") as fh:
        doc = tomllib.loads(fh.read())
    assert doc["id"] == "mi-mod"
    assert doc["version"] == "0.1.0"
    assert doc["game"] == ["2.0.1a"]
    assert doc["mod_format"] == 1
    assert set(doc) <= CLAVES_DE_NEW, "claves inventadas: %s" % (set(doc) - CLAVES_DE_NEW)
    assert not any(key == "mod" for key in doc), \
        "el id de Modtopia va en la raiz, no en una tabla [mod] (mt_manifest.c:149-156)"


def test_2_validate_acepta_el_mod_toml_con_exit_0(tmp_path, capsys):
    destino = _new(tmp_path)
    assert main(["mod", "validate", destino, "--no-container"]) == 0
    assert "resultado: OK" in capsys.readouterr().out


# --------------------------------------------------------------------------
# 3: el legado sigue cargando
# --------------------------------------------------------------------------

def test_3a_paquete_viejo_con_mod_json_en_carpeta_sigue_cargando(tmp_path):
    with helpers.records_spec():
        payload = helpers.records_payload({1: b"\x00" * 8, 2: b"\x00" * 8})
        cont = helpers.make_container(str(tmp_path / "copia"),
                                      {helpers.REC_TABLE: payload})
    doc = helpers.base_doc(cont, "mod-viejo")
    doc["edits"] = [{"table": helpers.REC_TABLE, "row": 1, "offset": 0,
                     "type": "u32", "expect": "0", "value": "7", "why": "legado"}]
    ruta = helpers.write_mod(str(tmp_path / "viejo"), doc)      # escribe mod.json
    assert os.path.basename(ruta) == LEGACY_MANIFEST
    mod = load_mod(os.path.dirname(ruta))
    assert mod.report.ok, [str(i) for i in mod.report.issues]
    assert mod.manifest.endswith(LEGACY_MANIFEST)
    assert mod.name == "mod-viejo"
    assert len(mod.edits) == 1
    # `check_expect=False`: el `expect` contra el payload sintetico no es asunto
    # de este test, que es que el manifiesto legado cargue y valide igual.
    rep = validate(mod, cont, check_expect=False)
    assert rep.ok, [str(i) for i in rep.issues]
    assert main(["mod", "validate", os.path.dirname(ruta), "--no-container"]) == 0


def test_3b_paquete_viejo_pkmod_con_mod_json_en_la_raiz(tmp_path):
    doc = helpers.mod_romfs_doc("viejo-paquete", [
        {"path": "motor_asset/x.bin", "file": "payload/x.bin", "why": "legado"}])
    paquete = os.path.join(str(tmp_path), "viejo.pkmod")
    with zipfile.ZipFile(paquete, "w") as zf:
        zf.writestr(LEGACY_MANIFEST, json.dumps(doc))
        zf.writestr("payload/x.bin", b"contenido")
    mod = Origen(paquete).leer_manifest()
    assert mod.report.ok, [str(i) for i in mod.report.issues]
    assert mod.name == "viejo-paquete"
    assert len(mod.romfs) == 1


def test_3c_los_dos_formatos_cargan_lo_mismo(tmp_path):
    """Mismo contenido, dos envolturas: el `Mod` que sale es el mismo."""
    doc = helpers.mod_romfs_doc("mismo", [
        {"path": "motor_asset/x.bin", "file": "payload/x.bin", "why": "x",
         "size": 3, "sha256": "a" * 64, "original_sha256": "b" * 64}],
        requires=[{"id": "otro-mod", "version": "^1.0"}])
    doc["edits"] = [{"table": 983, "row": 63, "offset": 34, "type": "u16",
                     "expect": 2997, "value": 2998, "why": "celda"}]
    doc["text"] = [{"table": 4650, "id": 3001, "slot": 0,
                    "expect_sha256": "c" * 64, "value": "Banco", "why": "texto"}]
    json_dir = str(tmp_path / "json")
    toml_dir = str(tmp_path / "toml")
    helpers.write_mod(json_dir, doc)                       # legado
    os.makedirs(toml_dir, exist_ok=True)
    with open(os.path.join(toml_dir, MANIFEST), "w", encoding="utf-8") as fh:
        fh.write(dumps(doc))
    a = load_mod(json_dir)
    b = load_mod(toml_dir)
    assert a.report.ok, [str(i) for i in a.report.issues]
    assert b.report.ok, [str(i) for i in b.report.issues]
    for campo in ("name", "version", "title", "game_version", "container_md5",
                  "authors", "requires", "files", "mod_format"):
        assert getattr(a, campo) == getattr(b, campo), campo
    assert [e.as_dict() for e in a.edits] == [e.as_dict() for e in b.edits]
    assert [t.as_dict() for t in a.texts] == [t.as_dict() for t in b.texts]
    assert [f.as_dict() for f in a.romfs] == [f.as_dict() for f in b.romfs]


# --------------------------------------------------------------------------
# El id tiene que valer para los dos lectores
# --------------------------------------------------------------------------

def test_id_invalido_no_se_escribe(tmp_path, capsys):
    with helpers.records_spec():
        cont = helpers.make_container(str(tmp_path / "c"), {1: b"x" * 10})
        destino = str(tmp_path / "con-punto")
        # '.' esta bien en `name` del kit, pero Modtopia lo rechaza (mt_id_valid)
        assert main(["mod", "new", "mi.mod", "--dir", destino,
                     "--container", cont.dir]) == 2
    salidas = capsys.readouterr()
    assert "mt_id_valid" in salidas.out + salidas.err
    assert not os.path.exists(destino)


def test_id_invalido_al_leer_es_error_de_informe(tmp_path):
    os.makedirs(str(tmp_path / "m"), exist_ok=True)
    with open(os.path.join(str(tmp_path / "m"), MANIFEST), "w", encoding="utf-8") as fh:
        fh.write('id = "mi.mod"\nversion = "0.1.0"\ngame = ["2.0.1a"]\n'
                 'mod_format = 1\ntitle = "pokopia"\n'
                 'container_md5 = { "LD_C0_R.BIN" = "%s", "LI_C0_R.IDX" = "%s" }\n'
                 % ("0" * 32, "1" * 32))
    mod = load_mod(str(tmp_path / "m"))
    assert not mod.report.ok
    assert any(i.code == "schema.id" for i in mod.report.errors)


def test_id_ausente_se_reporta_como_id_y_no_como_name(tmp_path):
    os.makedirs(str(tmp_path / "m"), exist_ok=True)
    with open(os.path.join(str(tmp_path / "m"), MANIFEST), "w", encoding="utf-8") as fh:
        fh.write('version = "0.1.0"\ngame = ["2.0.1a"]\n')
    mod = load_mod(str(tmp_path / "m"))
    errores = [i for i in mod.report.errors if i.code == "schema.id"]
    assert errores, [str(i) for i in mod.report.issues]
    assert "falta 'id'" in errores[0].message


# --------------------------------------------------------------------------
# La seccion de celdas de F19 viaja en el mismo fichero
# --------------------------------------------------------------------------

def test_19_seccion_de_celdas_de_f19_viaja_sin_que_el_kit_la_rechace(tmp_path):
    os.makedirs(str(tmp_path / "celdas"), exist_ok=True)
    with open(os.path.join(str(tmp_path / "celdas"), MANIFEST), "w",
              encoding="utf-8") as fh:
        fh.write(
            'id = "celdas"\nversion = "0.1.0"\ngame = ["2.0.1a"]\n'
            'mod_format = 1\ntitle = "pokopia"\n'
            'container_md5 = { "LD_C0_R.BIN" = "%s", "LI_C0_R.IDX" = "%s" }\n'
            'contract = "1"\npriority = 0\n\n'
            '[[set]]\ntable = 983\nrow = 63\noffset = 34\ntype = "u16"\n'
            'value = 2998\n\n'
            '[[add]]\ntable = 983\ncopy_from = 63\n'
            'why = "nameIndex: u16 at +34; the text id is nameIndex + 3"\n'
            % ("0" * 32, "1" * 32))
    mod = load_mod(str(tmp_path / "celdas"))
    assert mod.report.ok, [str(i) for i in mod.report.issues]
    assert main(["mod", "validate", str(tmp_path / "celdas"),
                 "--no-container"]) == 0
    # la seccion esta en el documento, no desaparece al cargarla
    assert mod.doc["contract"] == "1"
    assert mod.doc["set"] == [{"table": 983, "row": 63, "offset": 34,
                               "type": "u16", "value": 2998}]
    assert mod.doc["add"] == [{"table": 983, "copy_from": 63,
                               "why": "nameIndex: u16 at +34; "
                                      "the text id is nameIndex + 3"}]
    # y si el kit reescribe el manifiesto, la seccion se queda
    otra = str(tmp_path / "celdas-otra")
    os.makedirs(otra, exist_ok=True)
    with open(os.path.join(otra, MANIFEST), "w", encoding="utf-8") as fh:
        fh.write(dumps(mod.doc))
    de_vuelta = load_mod(otra)
    assert de_vuelta.report.ok, [str(i) for i in de_vuelta.report.issues]
    assert de_vuelta.doc["contract"] == "1"
    assert de_vuelta.doc["set"] == mod.doc["set"]


# --------------------------------------------------------------------------
# Escribir y leer, idempotente
# --------------------------------------------------------------------------

def test_dumps_loads_es_idempotente(tmp_path):
    doc = helpers.mod_romfs_doc("idem", [
        {"path": "motor_asset/x.bin", "file": "payload/x.bin", "why": "x"}],
        requires=[{"id": "otro-mod", "version": "^1.0"}],
        description='texto con "comillas", \\ barra y\nsalto de linea')
    doc["edits"] = [{"table": 983, "row": 63, "offset": 34, "type": "u16",
                     "expect": 2997, "value": 2998, "why": "celda"}]
    doc["merged_from"] = [{"name": "a", "version": "0.1.0"},
                          {"name": "b", "version": "0.2.0"}]
    texto = dumps(doc)
    assert dumps(doc) == texto, "el mismo documento tiene que dar el mismo texto"
    carpeta = str(tmp_path / "idem")
    os.makedirs(carpeta, exist_ok=True)
    with open(os.path.join(carpeta, MANIFEST), "w", encoding="utf-8") as fh:
        fh.write(texto)
    mod = load_mod(carpeta)
    assert mod.report.ok, [str(i) for i in mod.report.issues]
    assert dumps(mod.doc) == texto


def test_toml_roto_da_mod_error_con_codigo_toml(tmp_path):
    os.makedirs(str(tmp_path / "roto"), exist_ok=True)
    with open(os.path.join(str(tmp_path / "roto"), MANIFEST), "w",
              encoding="utf-8") as fh:
        fh.write('id = "roto\n')
    with pytest.raises(ModError) as exc:
        load_mod(str(tmp_path / "roto"))
    assert exc.value.code == "toml"
    assert exc.value.exit_code != 0


def test_en_la_misma_carpeta_manda_el_toml(tmp_path):
    with helpers.records_spec():
        cont = helpers.make_container(str(tmp_path / "c"), {1: b"\x00" * 8})
    doc = helpers.base_doc(cont, "mod-nuevo")
    carpeta = str(tmp_path / "dos")
    helpers.write_mod(carpeta, doc)                       # legado
    with open(os.path.join(carpeta, MANIFEST), "w", encoding="utf-8") as fh:
        fh.write(dumps(dict(doc, name="mod-adoptado")))
    mod = load_mod(carpeta)
    assert mod.report.ok, [str(i) for i in mod.report.issues]
    assert mod.name == "mod-adoptado"
    assert mod.manifest.endswith(MANIFEST)


def test_id_problema_cubre_las_reglas_de_modtopia():
    assert id_problema("mi-mod") is None
    assert id_problema("m") is not None              # menos de 2 caracteres
    assert id_problema("mi.mod") is not None         # el punto no vale
    assert id_problema("1mod") is not None           # tiene que empezar por letra
    assert id_problema("mi mod") is not None         # espacio
    assert id_problema("m" * 65) is not None         # mas de 64
