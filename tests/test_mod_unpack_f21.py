"""M9 · F21 §2: `pkp mod unpack` extrae y `--diff` nombra celdas.

Contenedor sintético: tabla #983 real del registro (count 4600, stride 68),
con la celda base `0x0e6a` en fila 63 +34. El dump nunca se abre para escribir.
"""

from __future__ import annotations

import hashlib
import os
import struct
import zipfile

import pytest

from pokopia.cli import main

from tests import helpers

ANTES = 0x0E6A
DESPUES = 0x0BB6
LINEA = "#983 fila 63 +34 0x0e6a → 0x0bb6"

BASE = """id = "m9-demo"
version = "0.1.0"
name = "Demo M9"
authors = ["tests"]
game = ["2.0.1a"]
title = "pokopia"
contract = "1"
mod_format = 1
container_md5 = { "LD_C0_R.BIN" = "00000000000000000000000000000000", "LI_C0_R.IDX" = "11111111111111111111111111111111" }
"""

SET = """
[[set]]
table = 983
row = 63
offset = 34
type = "u16"
value = {value}
"""

ESQUEMA = """[[fields]]
name = "nameIndex"
offset = 34
type = "u16"
"""


@pytest.fixture
def dump(tmp_path):
    fila = bytearray(68)
    struct.pack_into("<H", fila, 34, ANTES)
    payload = helpers.records_payload({63: bytes(fila)}, count=4600, stride=68,
                                      version=3)
    return helpers.make_container(str(tmp_path / "dump"), {983: payload},
                                  entries=984)


def paquete(tmp_path, contenido=SET.format(value=DESPUES), extra=None):
    ruta = tmp_path / "demo.pkmod"
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mod.toml", BASE + contenido)
        zf.writestr("data/nota.txt", "extraido sin tocar el dump\n")
        for nombre, datos in (extra or {}).items():
            zf.writestr(nombre, datos)
    return str(ruta)


def huellas(cont):
    return {os.path.basename(p): hashlib.sha256(open(p, "rb").read()).hexdigest()
            for p in (cont.idx, cont.bin)}


@pytest.fixture(autouse=True)
def sin_dump_por_defecto(monkeypatch):
    monkeypatch.delenv("PKP_ROMFS", raising=False)


def test_1_unpack_extrae_sin_tocar_dump(tmp_path, dump, capsys):
    antes = huellas(dump)
    ficheros_antes = sorted(os.listdir(dump.dir))
    destino = tmp_path / "salida"

    assert main(["mod", "unpack", paquete(tmp_path), "-o", str(destino)]) == 0
    salida = capsys.readouterr().out
    assert "extraido: %s (2 fichero(s))" % destino in salida
    assert "diff: omitido (sin --dump)" in salida
    assert (destino / "mod.toml").is_file()
    assert (destino / "data" / "nota.txt").read_text(encoding="utf-8").startswith("extraido")
    assert huellas(dump) == antes
    assert sorted(os.listdir(dump.dir)) == ficheros_antes


def test_2_diff_usa_el_formato_del_spec(tmp_path, dump, capsys):
    antes = huellas(dump)
    destino = tmp_path / "salida-diff"

    assert main(["mod", "unpack", paquete(tmp_path), "-o", str(destino),
                 "--diff", dump.dir]) == 0
    salida = capsys.readouterr().out
    assert LINEA in salida, salida
    assert "diff: 1 celda(s) cambiada(s) de 1 declarada(s)" in salida
    assert "%s (solo lectura)" % dump.dir in salida
    assert huellas(dump) == antes


def test_3_celda_igual_no_aparece_en_el_diff(tmp_path, dump, capsys):
    destino = tmp_path / "salida-igual"
    assert main(["mod", "unpack", paquete(tmp_path, SET.format(value=ANTES)),
                 "-o", str(destino), "--diff", dump.dir]) == 0
    salida = capsys.readouterr().out
    assert "diff: 0 celda(s) cambiada(s) de 1 declarada(s)" in salida
    assert LINEA not in salida


def test_4_diff_rechaza_destino_dentro_del_dump(tmp_path, dump, capsys):
    antes = huellas(dump)
    assert main(["mod", "unpack", paquete(tmp_path), "-o",
                 os.path.join(dump.dir, "salida"), "--diff", dump.dir]) == 2
    error = capsys.readouterr().err
    assert "destino protegido" in error
    assert huellas(dump) == antes
    assert not os.path.exists(os.path.join(dump.dir, "salida"))


def test_5_campo_por_nombre_con_esquema(tmp_path, dump, capsys):
    contenido = """
[[set]]
table = 983
row = 63
field = "nameIndex"
type = "u16"
value = {value}
""".format(value=DESPUES)
    assert main(["mod", "unpack", paquete(tmp_path, contenido,
                 {"tables/983.toml": ESQUEMA}),
                 "-o", str(tmp_path / "salida-campo"), "--diff", dump.dir]) == 0
    assert LINEA in capsys.readouterr().out


def test_6_legacy_edits_tambien_se_difiere(tmp_path, dump, capsys):
    contenido = """
[[edits]]
table = 983
row = 63
offset = 34
type = "u16"
expect = 3738
value = 2998
why = "regresion del formato anterior"
"""
    assert main(["mod", "unpack", paquete(tmp_path, contenido),
                 "-o", str(tmp_path / "salida-legacy"), "--diff", dump.dir]) == 0
    assert LINEA in capsys.readouterr().out


def test_7_celda_fuera_de_rango_no_escribe(tmp_path, dump, capsys):
    destino = tmp_path / "salida-mala"
    contenido = SET.format(value=DESPUES).replace("row = 63", "row = 99999")
    assert main(["mod", "unpack", paquete(tmp_path, contenido), "-o", str(destino),
                 "--diff", dump.dir]) == 1
    error = capsys.readouterr().err
    assert "fuera de rango" in error
    assert not destino.exists()


def test_8_entrada_de_zip_escape_no_se_extrae(tmp_path, dump, capsys):
    destino = tmp_path / "salida-slip"
    assert main(["mod", "unpack", paquete(tmp_path, extra={"../salida.txt": "mal"}),
                 "-o", str(destino)]) == 1
    assert "entrada de paquete insegura" in capsys.readouterr().err
    assert not destino.exists()
    assert not (tmp_path / "salida.txt").exists()


def test_9_repetir_pide_forzar_y_forzar_es_idempotente(tmp_path, dump, capsys):
    paquete_ = paquete(tmp_path)
    destino = tmp_path / "salida-repetida"
    assert main(["mod", "unpack", paquete_, "-o", str(destino)]) == 0
    capsys.readouterr()
    assert main(["mod", "unpack", paquete_, "-o", str(destino)]) == 2
    assert "ya tiene ficheros" in capsys.readouterr().err
    assert main(["mod", "unpack", paquete_, "-o", str(destino), "--forzar"]) == 0
    assert "extraido: %s (2 fichero(s))" % destino in capsys.readouterr().out
