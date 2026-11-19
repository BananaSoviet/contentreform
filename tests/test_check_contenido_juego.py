"""Compuerta T10: la lista de cadenas del juego viaja en tools/ y se aplica.

Este fichero **viaja en la release** (tests/ esta en la WHITELIST), asi que no
puede contener las cadenas literales: se componen en tiempo de ejecucion para no
disparar el propio guardián que comprueba.
"""

from __future__ import annotations

from pathlib import Path

from tools import check_contenido_juego as cc

# Compuestas en tiempo de ejecucion: este fichero viaja en la release y el
# guardián tambien lo escanea. Las diez cadenas del hallazgo T10 ronda 2 mas las
# ocho de §12.3 no pueden aparecer aqui como literales.
SEMILLAS = {
    "baya " + "atania",
    "regalo-" + "dipplin",
    "ha" + "ba",
    "amuleto " + "puro",
    "lodo " + "negro",
    "res" + "tos",
    "huevo " + "suerte",
    "mesa " + "natural",
    "escudo " + "habilidad",
    "regalo " + "de",
    "sofá " + "chic",
    "chic " + "sofa",
    "alfombra redonda " + "pequeña",
    "small round " + "rug",
    "cama de " + "camarote",
    "guest-room " + "bed",
    "cama " + "antigua",
    "antique " + "bed",
}
CADENA_OBJETO = next(s for s in SEMILLAS if s.startswith("baya"))
CADENA_PERSONAJE = next(s for s in SEMILLAS if s.startswith("regalo-"))


def test_la_lista_es_la_semilla_medida_en_t10():
    assert set(cc.CADENAS_PROHIBIDAS) == SEMILLAS


def test_cada_semilla_prohibida_falla_con_ruta_y_linea(tmp_path: Path):
    for indice, cadena in enumerate(sorted(SEMILLAS)):
        fichero = tmp_path / ("caso-%02d.md" % indice)
        fichero.write_text("limpio\n%s en la linea dos\n" % cadena, encoding="utf-8")
        codigo, salida = cc.comprobar(tmp_path)
        assert codigo == 1, cadena
        assert "caso-%02d.md:2:" % indice in salida, cadena
        fichero.unlink()


def test_un_artefacto_sin_cadenas_pasa(tmp_path: Path):
    (tmp_path / "SPEC.md").write_text(
        "id 2284 (nombre del juego no reproducido)\n", encoding="utf-8")
    codigo, salida = cc.comprobar(tmp_path)
    assert codigo == 0
    assert "0 cadenas del juego" in salida


def test_la_cadena_de_objeto_falla_con_ruta_y_linea(tmp_path: Path):
    (tmp_path / "SPEC.md").write_text(
        "limpio\n%s en la linea dos\n" % CADENA_OBJETO.title(), encoding="utf-8")
    codigo, salida = cc.comprobar(tmp_path)
    assert codigo == 1
    assert "SPEC.md:2:" in salida
    assert CADENA_OBJETO in salida


def test_la_cadena_de_personaje_falla_y_el_binario_se_ignora(tmp_path: Path):
    (tmp_path / "tests.py").write_text(
        'name = "%s"\n' % CADENA_PERSONAJE, encoding="utf-8")
    (tmp_path / "blob.bin").write_bytes(bytes([0xFF, 0xFE, 0x00]))
    codigo, salida = cc.comprobar(tmp_path)
    assert codigo == 1
    assert "tests.py:1:" in salida
    assert CADENA_PERSONAJE in salida


def test_los_tests_que_viajan_no_contienen_las_semillas():
    raiz = Path(__file__).resolve().parent.parent / "tests"
    hallazgos, _leidos = cc.escanear(raiz)
    assert hallazgos == []
