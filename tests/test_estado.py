"""`pkp estado`: bloque generado de `docs/ESTADO-AHORA.md` (TSV + git).

Cubre lo que exige la tarjeta `t_bbafd081`: conteo desde un TSV de prueba,
`--write` idempotente que respeta el resto del fichero byte a byte,
`--check` rojo con la pagina de hace 4 dias y con el bloque manipulado, y
`--check` verde en el fichero real recien generado.

Los tests sinteticos clavan `ultimo_commit` a `None` para que no dependan
del HEAD vivo del repo (que se mueve mientras hay sesiones abiertas); el
unico test que mira el repo real es el ultimo, y a proposito.

La tarjeta `t_b4961d90` anade el ciclo (generar -> commitear -> `--check`
= 0) y el caso rebase (HEAD no desciende del citado -> fallo), los dos en
un repo temporal: el sello exige ascendencia, no igualdad.
"""

from __future__ import annotations

import datetime as dt
import os
import subprocess

from pokopia import estado_ahora as est
from pokopia.cli import main

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FILAS = [
    ("A1", "texto cambiado", "sí · FIRMADA 12-nov"),
    ("B1", "fila nueva", "NO"),
    ("C1", "parche H4", "sí · FIRMADA 13-nov"),
]


def _tsv(ruta, filas=FILAS) -> str:
    """TSV minimo con las tres columnas que lee el comando."""
    lineas = ["id\tvehículo\tlisto\truta\tcomando\tqué mirar"]
    for ident, vehiculo, listo in filas:
        lineas.append("%s\t%s\t%s\t-\t-\tprueba" % (ident, vehiculo, listo))
    ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return str(ruta)


def _pagina(ruta, fecha: dt.date, commit, bloque="BASURA A MANO") -> str:
    """Pagina minima con la cabecera estilo ESTADO-AHORA y los marcadores."""
    fecha_txt = est.fecha_texto(fecha)
    caduca = est.fecha_texto(fecha + dt.timedelta(days=est.CADUCIDAD_DIAS))
    ruta.write_text(
        "# ESTADO AHORA — ContentReForm\n"
        "\n"
        "**%s** · commit `%s` · **caduca el %s**. Si tiene más de tres días: "
        "se remide, no se cita.\n"
        "\n"
        "Texto de Edu que no se toca.\n"
        "\n"
        "%s\n"
        "%s\n"
        "%s\n"
        "\n"
        "Cola del fichero, también intacta.\n"
        % (fecha_txt, commit, caduca, est.MARCA_INI, bloque, est.MARCA_FIN),
        encoding="utf-8")
    return str(ruta)


def _fuera(ruta: str) -> bytes:
    """Los bytes del fichero fuera del bloque generado."""
    data = open(ruta, "rb").read()
    i = data.find(est.MARCA_INI.encode("utf-8"))
    j = data.find(est.MARCA_FIN.encode("utf-8"))
    assert i >= 0 and j > i, "marcadores no encontrados en %s" % ruta
    return data[:i] + data[j:]


def test_tsv_de_prueba_da_el_conteo(tmp_path):
    """Conteo: solo cuenta 'firmada' en la columna `listo`."""
    ruta = _tsv(tmp_path / "u.tsv")
    filas = est.leer_unidades(ruta)
    assert [f["id"] for f in filas] == ["A1", "B1", "C1"]
    assert [f["id"] for f in filas if f["firmada"]] == ["A1", "C1"]


def test_firmada_solo_marca_estructurada_no_mencion_en_prosa(tmp_path):
    """t_f36395f3: «firmada» en una nota en prosa NO cuenta; la marca
    estructurada `sí · FIRMADA ...` sí. Es la causa del unico fallo del
    19-nov: la celda de B1 dice «prueba 3 firmada» y no es una firma."""
    filas = [
        ("B1", "fila nueva",
         "no firmable — banco 19-nov 03:09 = HABILITADOR COMPLETO, no firma: "
         "objeto nuevo (prueba 3 firmada); sin nombre ni modelo 3D"),
        ("C9", "otra fila", "sí · FIRMADA 19-nov"),
    ]
    ruta = _tsv(tmp_path / "u.tsv", filas)
    por_id = {f["id"]: f for f in est.leer_unidades(ruta)}
    assert por_id["B1"]["firmada"] is False, \
        "una mención de «firmada» en prosa no puede contar como firma"
    assert por_id["C9"]["firmada"] is True, \
        "la marca estructurada `sí · FIRMADA ...` sí cuenta como firma"


def test_estado_imprime_el_conteo_del_tsv_de_prueba(tmp_path, capsys):
    tsv = _tsv(tmp_path / "u.tsv")
    pag = _pagina(tmp_path / "p.md", dt.date.today(), "abc1234")
    assert main(["estado", "--tsv", tsv, "--pagina", pag]) == 0
    salida = capsys.readouterr().out
    assert "2 de 3 unidades" in salida
    assert "| A1 | texto cambiado | sí · FIRMADA 12-nov |" in salida
    assert "| B1 |" not in salida, "una unidad sin firmar no sale en la tabla"
    assert "versión" in salida and "commit" in salida
    assert salida.endswith("\n")


def test_tsv_real_del_repo():
    """El TSV del repo: 22 unidades; firmadas, las que dicen FIRMADA.

    11 el 18-nov tras el volcado `t_cd09bae0` (entro A6). Si se firma otra
    unidad, se actualiza aqui: el titulo de la pagina lo dira solo.
    """
    filas = est.leer_unidades(os.path.join(RAIZ, est.TSV_POR_DEFECTO))
    firmadas = [f["id"] for f in filas if f["firmada"]]
    assert len(filas) == 22
    assert firmadas == ["A1", "A2", "A6", "A7", "C1",
                        "D1", "D2", "D3", "D4", "D5", "E2"]


def test_write_dos_veces_no_cambia_el_fichero(tmp_path, capsys):
    """Idempotente: la segunda `--write` ni siquiera escribe."""
    tsv = _tsv(tmp_path / "u.tsv")
    pag = _pagina(tmp_path / "p.md", dt.date.today(), "abc1234")
    assert main(["estado", "--write", pag, "--tsv", tsv]) == 0
    assert "escrito" in capsys.readouterr().out
    primera = open(pag, "rb").read()
    assert main(["estado", "--write", pag, "--tsv", tsv]) == 0
    assert "sin cambios" in capsys.readouterr().out
    assert open(pag, "rb").read() == primera, "la segunda --write cambio el fichero"
    assert b"BASURA A MANO" not in primera, "el bloque de mano seguia dentro"
    assert b"| A1 |" in primera


def test_write_respeta_el_resto_byte_a_byte(tmp_path, capsys):
    """Lo que esta fuera de los marcadores no cambia ni un byte."""
    tsv = _tsv(tmp_path / "u.tsv")
    pag = _pagina(tmp_path / "p.md", dt.date.today(), "abc1234")
    antes = _fuera(pag)
    assert main(["estado", "--write", pag, "--tsv", tsv]) == 0
    capsys.readouterr()
    assert _fuera(pag) == antes, "el resto del fichero se toco"
    dentro = open(pag, "rb").read()
    assert est.MARCA_INI.encode("utf-8") in dentro
    assert est.MARCA_FIN.encode("utf-8") in dentro


def test_check_falla_con_pagina_de_cuatro_dias(tmp_path, capsys, monkeypatch):
    """(a) la pagina caducada: exit 1, y el motivo es la frescura."""
    monkeypatch.setattr(est, "ultimo_commit", lambda raiz: None)
    tsv = _tsv(tmp_path / "u.tsv")
    cuatro = dt.date.today() - dt.timedelta(days=est.CADUCIDAD_DIAS + 1)
    pag = _pagina(tmp_path / "p.md", cuatro, "abc1234")
    # se genera primero: el unico problema que tiene que quedar es la edad
    assert main(["estado", "--write", pag, "--tsv", tsv]) == 0
    capsys.readouterr()
    assert main(["estado", "--check", "--pagina", pag, "--tsv", tsv]) == 1
    salida = capsys.readouterr().out
    fallos = [l for l in salida.splitlines() if l.startswith("FALLO:")]
    assert len(fallos) == 1, salida
    assert "4 dias" in fallos[0], salida
    assert est.fecha_texto(cuatro) in fallos[0], \
        "el motivo no dice la fecha de la cabecera: %s" % fallos[0]


def test_check_falla_con_bloque_manipulado(tmp_path, capsys, monkeypatch):
    """(b) alguien edito el bloque a mano y no regenero: exit 1."""
    monkeypatch.setattr(est, "ultimo_commit", lambda raiz: None)
    tsv = _tsv(tmp_path / "u.tsv")
    pag = _pagina(tmp_path / "p.md", dt.date.today(), "abc1234")
    assert main(["estado", "--write", pag, "--tsv", tsv]) == 0
    capsys.readouterr()
    texto = open(pag, encoding="utf-8", newline="").read()
    assert texto.count("| A1 |") == 1
    with open(pag, "w", encoding="utf-8", newline="") as fh:
        fh.write(texto.replace("| A1 |", "| A9 |"))
    assert main(["estado", "--check", "--pagina", pag, "--tsv", tsv]) == 1
    salida = capsys.readouterr().out
    assert "no coincide" in salida, salida


def test_check_sin_marcadores_no_toca_nada(tmp_path, capsys):
    """Sin marcadores: --write no escribe (exit 2) y --check dice que faltan."""
    tsv = _tsv(tmp_path / "u.tsv")
    pag = tmp_path / "sin-marcadores.md"
    contenido = "# pagina\n\nsin marcadores aqui.\n"
    pag.write_text(contenido, encoding="utf-8", newline="")
    assert main(["estado", "--write", str(pag), "--tsv", tsv]) == 2
    err = capsys.readouterr().err
    assert "marcadores" in err, err
    with open(pag, encoding="utf-8", newline="") as fh:
        assert fh.read() == contenido, \
            "un --write sin marcadores no puede tocar el fichero"
    assert main(["estado", "--check", "--pagina", str(pag), "--tsv", tsv]) == 1
    assert "marcadores" in capsys.readouterr().out


def test_sin_git_lo_dice(tmp_path):
    """Sin git no revienta: `ultimo_commit` devuelve None y el bloque sigue."""
    (tmp_path / ".git").write_text("gitdir: no-existe", encoding="utf-8")
    assert est.ultimo_commit(str(tmp_path)) is None


def _repo_temporal(tmp_path):
    """`(raiz, git, c1)` de un repo git de prueba con un commit base.

    `git(*args)` se ejecuta dentro del repo y revienta la asercion si git
    falla; `c1` es el HEAD corto tras ese commit base.
    """
    raiz = tmp_path / "repo"
    (raiz / "docs").mkdir(parents=True)

    def git(*args):
        res = subprocess.run(["git", *args], cwd=str(raiz),
                             capture_output=True, text=True, timeout=60)
        assert res.returncode == 0, res.stderr
        return res.stdout.strip()

    git("init", "-q")
    git("config", "user.email", "prueba@local")
    git("config", "user.name", "prueba")
    git("config", "commit.gpgsign", "false")
    git("commit", "-q", "--allow-empty", "-m", "commit base")
    return str(raiz), git, git("rev-parse", "--short", "HEAD")


def test_ciclo_generar_commitear_check_cero(tmp_path, monkeypatch, capsys):
    """`t_b4961d90`: generar -> commitear -> `pkp estado --check` = 0.

    El commit de la propia pagina mueve HEAD despues de `--write`: el
    chequeo exige que HEAD descienda del sello, no que sean iguales, y el
    `--write` posterior no reescribe (lo unico que cambio es el sello).
    Repo temporal: en el real, commitear es cosa de Edu, no del test.
    """
    raiz, git, c1 = _repo_temporal(tmp_path)
    monkeypatch.setattr(est, "raiz_por_defecto", lambda: raiz)
    docs = tmp_path / "repo" / "docs"
    _tsv(docs / "ESTADO-VEHICULOS.tsv")
    pag = _pagina(docs / "ESTADO-AHORA.md", dt.date.today(), c1)

    assert main(["estado", "--write", pag]) == 0
    assert "escrito" in capsys.readouterr().out

    # el commit de la propia pagina: mueve HEAD
    git("add", "docs/ESTADO-AHORA.md")
    git("commit", "-q", "-m", "pagina de estado")
    assert git("rev-parse", "--short", "HEAD") != c1

    # nada nuevo: --write ni siquiera escribe y los bytes quedan iguales
    bytes_antes = open(pag, "rb").read()
    assert main(["estado", "--write", pag]) == 0
    assert "sin cambios" in capsys.readouterr().out
    assert open(pag, "rb").read() == bytes_antes, \
        "un --write sin nada nuevo toco el fichero"

    # el ciclo cierra: check con HEAD por delante de la cabecera
    codigo = main(["estado", "--check"])
    salida = capsys.readouterr().out
    assert codigo == 0, salida
    assert "resultado: OK" in salida


def test_check_falla_si_head_no_desciende_del_citado(tmp_path, monkeypatch,
                                                      capsys):
    """`t_b4961d90`: rebase o rama rara: el commit citado existe pero HEAD
    no desciende de el -> fallo, con el motivo correcto."""
    raiz, git, c1 = _repo_temporal(tmp_path)
    monkeypatch.setattr(est, "raiz_por_defecto", lambda: raiz)
    # un commit que despues se deja caer: existe en el repo, pero HEAD
    # (vuelto a c1) no desciende de el
    git("commit", "-q", "--allow-empty", "-m", "rama que se cae")
    c2 = git("rev-parse", "--short", "HEAD")
    git("reset", "-q", "--hard", c1)
    assert git("rev-parse", "--short", "HEAD") == c1

    docs = tmp_path / "repo" / "docs"
    _tsv(docs / "ESTADO-VEHICULOS.tsv")
    # la cabecera cita el commit caido; el bloque se estampa con HEAD (c1)
    pag = _pagina(docs / "ESTADO-AHORA.md", dt.date.today(), c2)
    assert main(["estado", "--write", pag]) == 0
    capsys.readouterr()
    codigo = main(["estado", "--check"])
    salida = capsys.readouterr().out
    assert codigo == 1, salida
    fallos = [l for l in salida.splitlines() if l.startswith("FALLO:")]
    assert len(fallos) == 1, salida
    assert "no es ancestro" in fallos[0], salida
    assert c2 in fallos[0], salida


def test_check_pasa_en_el_fichero_real_recien_generado(capsys):
    """La tarjeta: `--check` sobre el repo real con codigo 0.

    Si falla, es de verdad: la cabecera cita un commit del que HEAD no
    desciende, o la pagina caduco. Se remide y se reestampa; el test no
    se arregla a si mismo.
    """
    pagina = os.path.join(RAIZ, est.PAGINA_POR_DEFECTO)
    assert main(["estado", "--write", pagina]) == 0
    capsys.readouterr()
    codigo = main(["estado", "--check"])
    salida = capsys.readouterr().out
    assert codigo == 0, "el fichero real no cuadra:\n%s" % salida
