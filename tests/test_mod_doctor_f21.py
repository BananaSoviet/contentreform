"""M7 · F21 C4: `doctor` nombra el mod y la tabla que rompería el juego.

Regresión de la salida literal `#983 fila 63 +67`, del paquete limpio y de los
cuatro casos que pide la tarjeta: celda fuera de rango, conflicto sin `override`,
recuento de >1.000 celdas y `text` con idiomas sin rellenar.
"""

from __future__ import annotations

import os
import zipfile

import pytest

from pokopia.cli import main

DUMP = os.environ.get("PKP_ROMFS")

BASE = """id = "{ident}"
version = "0.1.0"
name = "{nombre}"
authors = ["m7"]
game = ["2.0.1a"]
title = "pokopia"
contract = "1"
mod_format = 1
"""

SETS = """
[[set]]
table = 983
row = {fila}
offset = {offset}
type = "u16"
value = {valor}
"""


def paquete(tmp_path, ident, nombre, extra="", md5bin="0" * 32, md5idx="1" * 32):
    destino = tmp_path / ident
    destino.mkdir()
    texto = BASE.format(ident=ident, nombre=nombre)
    texto += ('container_md5 = { "LD_C0_R.BIN" = "%s", "LI_C0_R.IDX" = "%s" }\n'
              % (md5bin, md5idx)) + extra
    (destino / "mod.toml").write_text(texto, encoding="utf-8", newline="\n")
    return destino


def celda(fila=63, offset=34, valor=2998):
    return SETS.format(fila=fila, offset=offset, valor=valor)


@pytest.fixture(autouse=True)
def sin_dump_por_defecto(monkeypatch):
    """Los tests de salida no dependen de qué dump tenga configurado el PC."""
    monkeypatch.delenv("PKP_ROMFS", raising=False)


def test_1_doctor_nombra_mod_y_tabla(tmp_path, capsys):
    paquete(tmp_path, "m7-malo", "mod roto M7", celda(offset=67))
    assert main(["mod", "doctor", str(tmp_path / "m7-malo")]) == 1
    salida = capsys.readouterr().out
    assert "FALLO" in salida
    assert "m7-malo" in salida
    assert "#983 fila 63 +67" in salida, salida
    assert "cruza el stride" in salida
    assert "resultado: FALLIDO (1 fallo(s)" in salida


def test_2_paquete_bueno_no_da_falsos_fallos(tmp_path, capsys):
    paquete(tmp_path, "m7-bueno", "mod bueno M7", celda())
    assert main(["mod", "doctor", str(tmp_path / "m7-bueno")]) == 0
    salida = capsys.readouterr().out
    assert "FALLO" not in salida
    assert "resultado: sano con avisos" in salida


def test_3_celda_fuera_de_rango_nombra_la_tabla(tmp_path, capsys):
    paquete(tmp_path, "m7-fuera", "fuera de rango", celda(fila=99999))
    assert main(["mod", "doctor", str(tmp_path / "m7-fuera")]) == 1
    salida = capsys.readouterr().out
    assert "#983 fila 99999 +34" in salida
    assert "fuera de rango (0..4599)" in salida
    assert "m7-fuera" in salida


def test_4_conflicto_sin_override_nombra_los_dos_mods(tmp_path, capsys):
    a = paquete(tmp_path, "m7-conf-a", "conflicto A", celda(valor=1))
    b = paquete(tmp_path, "m7-conf-b", "conflicto B", celda(valor=2))
    assert main(["mod", "doctor", str(a), str(b)]) == 1
    salida = capsys.readouterr().out
    assert "'m7-conf-a' y 'm7-conf-b'" in salida
    assert "#983 fila 63 +34" in salida
    assert "sin override" in salida

    # Un `override` en uno de los dos lo deja de ser: no hay falso conflicto.
    texto = (b / "mod.toml").read_text(encoding="utf-8")
    (b / "mod.toml").write_text(texto + "\noverride = true\n",
                                encoding="utf-8", newline="\n")
    capsys.readouterr()
    assert main(["mod", "doctor", str(a), str(b)]) == 0
    salida = capsys.readouterr().out
    assert "FALLO" not in salida and "sin override" not in salida


def test_5_aviso_de_mas_de_mil_celdas(tmp_path, capsys):
    paquete(tmp_path, "m7-muchas", "muchas celdas",
            "".join(celda(fila=i % 40) for i in range(1001)))
    assert main(["mod", "doctor", str(tmp_path / "m7-muchas")]) == 0
    salida = capsys.readouterr().out
    assert "aviso" in salida and "1001 celdas" in salida
    assert "F19-C6" in salida


def test_6_texto_con_idiomas_sin_rellenar(tmp_path, capsys):
    paquete(tmp_path, "m7-texto", "texto incompleto",
            '\n[[text]]\nid = 10\nlangs = ["es"]\nsingular = "hola"\nplural = "hola"\n')
    assert main(["mod", "doctor", str(tmp_path / "m7-texto")]) == 0
    salida = capsys.readouterr().out
    assert "aviso" in salida
    assert "m7-texto" in salida and "idiomas sin rellenar" in salida
    assert "jp, en, fr" in salida


def test_7_tambien_lee_un_pkmod(tmp_path, capsys):
    destino = paquete(tmp_path, "m7-pack", "desde paquete", celda(offset=67))
    paquete_zip = tmp_path / "m7-pack.pkmod"
    with zipfile.ZipFile(paquete_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(destino / "mod.toml", "mod.toml")
    assert main(["mod", "doctor", str(paquete_zip)]) == 1
    salida = capsys.readouterr().out
    assert "m7-pack" in salida and "#983 fila 63 +67" in salida


@pytest.mark.skipif(not DUMP, reason="sin PKP_ROMFS: no se mide la geometría del dump")
def test_8_geometria_contra_el_dump_real(tmp_path, capsys):
    paquete(tmp_path, "m7-real", "contra dump", celda())
    assert main(["mod", "doctor", str(tmp_path / "m7-real"), "--dump", DUMP]) == 0
    salida = capsys.readouterr().out
    assert "count 4600, version 3, stride 68 B, payload 312864 B" in salida
    assert "resultado: sano (0 fallo(s), 0 aviso(s))" in salida


def test_9_paquete_ilegible_es_fallo_y_no_traza(tmp_path, capsys):
    vacia = tmp_path / "sin-manifiesto"
    vacia.mkdir()
    assert main(["mod", "doctor", str(vacia)]) == 1
    salida = capsys.readouterr().out
    assert "FALLO doctor.paquete" in salida
    assert "sin-manifiesto" in salida
    assert "Traceback" not in salida
