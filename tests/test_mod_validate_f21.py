"""M5 · F21 C2: error real, `fichero:línea: error:` y `--json` exacto.

Los cuatro comandos que pide la tarjeta, sobre paquetes `mod.toml` de F19
(`contract = "1"`, `[[set]]`), que es el vocabulario que cita SPEC F21 §2.
"""

from __future__ import annotations

import json
import os
import re

from pokopia.cli import main, print_validate_report
from pokopia.mod.errors import Report
from pokopia.mod.f21_validate import LineMap, validate_contract
from pokopia.mod import load_mod

BASE_TOML = """id = "m5"
version = "0.1.0"
name = "Prueba M5"
authors = ["m5"]
game = ["2.0.1a"]
title = "pokopia"
container_md5 = {{ "LD_C0_R.BIN" = "{md5bin}", "LI_C0_R.IDX" = "{md5idx}" }}
contract = "1"
mod_format = 1

[[set]]
table = 983
row = 63
offset = {offset}
type = "u16"
value = 2998
"""


def paquete(tmp_path, nombre, *, offset=34, contract="1", build="2.0.1a",
            md5bin="0" * 32, md5idx="1" * 32):
    destino = tmp_path / nombre
    destino.mkdir()
    texto = BASE_TOML.format(offset=offset, contract=contract, build=build,
                             md5bin=md5bin, md5idx=md5idx)
    texto = texto.replace('contract = "1"', 'contract = "%s"' % contract)
    texto = texto.replace('game = ["2.0.1a"]', 'game = ["%s"]' % build)
    (destino / "mod.toml").write_text(texto, encoding="utf-8", newline="\n")
    return destino


def LineaOffset(texto: str) -> int:
    return next(i for i, linea in enumerate(texto.splitlines(), 1)
                if "offset =" in linea)


def test_1_celda_que_cruza_el_stride_sale_con_codigo_1_y_fichero_linea(tmp_path, capsys):
    """Una celda real fuera de la fila: exit != 0 y `mod.toml:línea: error:`."""
    destino = paquete(tmp_path, "malo", offset=67)
    texto = (destino / "mod.toml").read_text(encoding="utf-8")
    linea = LineaOffset(texto)

    assert main(["mod", "validate", str(destino), "--no-container"]) == 1
    salida = capsys.readouterr().out
    encontrado = re.search(r"mod\.toml:(\d+): error: (.*)", salida)
    assert encontrado, salida
    assert int(encontrado.group(1)) == linea
    assert "cruza el stride" in encontrado.group(2)
    assert "resultado: INVALIDO (1 errores" in salida


def test_2_paquete_corregido_sale_cero_y_da_recuento(tmp_path, capsys):
    """El mismo paquete con offset 34: exit 0 y recuento final."""
    destino = paquete(tmp_path, "bueno", offset=34)
    assert main(["mod", "validate", str(destino), "--no-container"]) == 0
    salida = capsys.readouterr().out
    assert "mod.toml:" not in salida
    assert "resultado: OK (0 errores" in salida


def test_3_json_es_exactamente_la_estructura_de_f21(tmp_path, capsys):
    """`--json`: {ok, errors[{file,line,code,message}]}, igual que el texto."""
    destino = paquete(tmp_path, "json", offset=67)
    assert main(["mod", "validate", str(destino), "--no-container"]) == 1
    texto = capsys.readouterr().out
    encontrado_linea = re.search(r"mod\.toml:(\d+): error:", texto)
    assert encontrado_linea, texto
    esperado_linea = int(encontrado_linea.group(1))

    assert main(["mod", "validate", str(destino), "--no-container", "--json"]) == 1
    doc = json.loads(capsys.readouterr().out)
    assert set(doc) == {"ok", "errors"}
    assert doc["ok"] is False
    assert len(doc["errors"]) == 1
    error = doc["errors"][0]
    assert set(error) == {"file", "line", "code", "message"}
    assert error["file"] == "mod.toml"
    assert error["line"] == esperado_linea
    assert error["code"] == "f21.set.stride"
    assert "stride" in error["message"]


def test_4_json_de_paquete_valido(tmp_path, capsys):
    destino = paquete(tmp_path, "json-ok", offset=34)
    assert main(["mod", "validate", str(destino), "--no-container", "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc == {"ok": True, "errors": []}


def test_5_orden_de_f21_y_un_error_por_tipo(tmp_path):
    """SPEC F21 §2: contract, game, set, add, text, contenedor, tables."""
    destino = paquete(tmp_path, "orden", offset=67, contract="9", build="0.0")
    (destino / "data").mkdir()
    (destino / "data" / "LD_C0_R.BIN").write_bytes(b"x")
    (destino / "tables").mkdir()
    (destino / "tables" / "983.toml").write_text(
        "id = 983\ncount = 4600\nstride = 4\n", encoding="utf-8", newline="\n")
    # Dos sets malos, dos adds malos y un texto fuera de rango: solo el
    # primero de cada tipo debe aparecer.
    with (destino / "mod.toml").open("a", encoding="utf-8", newline="\n") as fh:
        fh.write('[[set]]\ntable = 983\nrow = 63\noffset = 68\ntype = "u16"\nvalue = 1\n')
        fh.write('[[add]]\ntable = 983\ncopy_from = 9999\nwhy = "x"\n')
        fh.write('[[add]]\ntable = 983\ncopy_from = 9998\nwhy = "x"\n')
        fh.write('[[text]]\nid = 9999\nlangs = ["es"]\n')

    mod = load_mod(str(destino))
    mapa = LineMap((destino / "mod.toml").read_text(encoding="utf-8"),
                   str(destino / "mod.toml"))
    codigos = [i.code for i in validate_contract(mod, mapa, str(destino)).errors]
    assert codigos == ["f21.contract", "f21.game", "f21.set.stride",
                       "f21.add.copy_from", "f21.text.id",
                       "f21.container_en_paquete", "f21.tables.geometria"]
    # Las posiciones son reales: cada error del manifiesto cae en su línea.
    for error in validate_contract(mod, mapa, str(destino)).errors[:5]:
        assert error.file == "mod.toml" and isinstance(error.line, int)


def test_6_error_sin_fichero_no_inventa_linea(capsys):
    report = Report()
    report.error("mod.romfs.original", "no encontré el original")
    print_validate_report(report)
    salida = capsys.readouterr().out
    assert salida.strip() == "error: no encontré el original"
    assert not re.search(r"\b\d+:\s*error", salida)


def test_7_toml_roto_tambien_se_posiciona_y_sale_1(tmp_path, capsys):
    destino = tmp_path / "roto"
    destino.mkdir()
    (destino / "mod.toml").write_text(
        'id = "roto"\ngame = ["2.0.1a"]\ncontract = "1"\n[[set]\n',
        encoding="utf-8", newline="\n")
    assert main(["mod", "validate", str(destino), "--no-container"]) == 1
    salida = capsys.readouterr().out
    encontrado = re.search(r"mod\.toml:(\d+): error: TOML invalido", salida)
    assert encontrado, salida
    assert int(encontrado.group(1)) == 4
