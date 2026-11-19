"""Empaquetado declarado: `pkp` se instala y la version tiene un solo dueno.

Dos casillas de la 0.6 que, sin este test, se rompen en silencio:

1. `pyproject.toml` tiene que declarar el punto de entrada `pkp`
   (`[project.scripts]`) y el backend que lo construye (`[build-system]`).
   Sin eso, `pip install contentreform` no instala ningun comando y la
   documentacion (50 ficheros) manda a ejecutar uno que no existe;
2. la version tiene **un solo dueno**: `pokopia.__version__`, la que imprime
   `pkp --version`. `pyproject.toml` no lleva cifra escrita a mano: la
   declara `dynamic` y la resuelve `tool.setuptools.dynamic.version.attr`
   (opcion A de la tarjeta t_2d71193b).

No comprueba que el wheel se construya (eso es `uv build`, caro y de red): aqui
se mira la declaracion, que es lo que el backend va a leer.
"""

from __future__ import annotations

import pathlib
import tomllib

import pytest

import pokopia
from pokopia import cli

RAIZ = pathlib.Path(__file__).resolve().parent.parent
CFG = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))


def test_build_system_declarado():
    """Sin `[build-system]` no hay construccion reproducible que valga."""
    sistema = CFG.get("build-system", {})
    assert sistema.get("build-backend") == "setuptools.build_meta", sistema
    exigidos = sistema.get("requires", [])
    assert any(r.split(">=")[0] == "setuptools" for r in exigidos), exigidos


def test_pyproject_declara_el_comando_pkp():
    """`[project.scripts]` es el punto de entrada: sin el, no hay `pkp`."""
    scripts = CFG["project"].get("scripts", {})
    assert scripts.get("pkp") == "pokopia.cli:main", (
        "[project.scripts] no declara pkp o apunta a otro sitio: %r" % scripts
    )
    # el objetivo existe y es el CLI
    assert callable(cli.main)


def test_una_sola_fuente_de_version():
    """`pyproject.toml` no tiene cifra propia: manda `pokopia.__version__`."""
    proyecto = CFG["project"]
    assert "version" not in proyecto, (
        "pyproject.toml vuelve a llevar `version = ...` escrito a mano: "
        "dos dueños de la version (pyproject y pokopia.__version__)"
    )
    assert "version" in proyecto.get("dynamic", []), (
        "[project] no declara `dynamic = [\"version\"]`: %r" % proyecto.get("dynamic")
    )
    resuelve = CFG.get("tool", {}).get("setuptools", {}).get("dynamic", {})
    assert resuelve.get("version", {}).get("attr") == "pokopia.__version__", resuelve
    # y la cifra que manda existe
    assert pokopia.__version__


def test_pkp_version_imprime_la_version_del_paquete(capsys):
    """El `--version` del comando instalado imprime `pokopia.__version__`."""
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0, exc.value.code
    assert capsys.readouterr().out.strip() == pokopia.__version__
