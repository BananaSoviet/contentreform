"""Raiz del repo en sys.path y directorio de trabajo fijo.

Dos garantias, y las dos son defectos reales ya pagados (informe 4.1):

- la raiz del repo va **primero** en `sys.path`, para que `import pokopia` y
  `from tests import helpers` resuelvan a este repo y no a un paquete homonimo
  del entorno (el venv de Hermes tiene su propio `tests/`);
- el directorio de trabajo se fija a la raiz, porque varios tests usan rutas
  relativas (`ejemplos/editar-fila`) y antes daban resultados distintos segun
  desde donde se lanzara pytest.
"""

import os
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

#: `tools/` NO viaja en la release (lista blanca de build_release.py). Estos
#: modulos importan scripts de ahi, asi que dentro del artefacto no pueden
#: recolectarse: se omiten solo ahi, con el mismo criterio con el que otros
#: tests del repo se saltan con `allow_module_level=True` cuando tools/ falta.
#: En el arbol de trabajo (con tools/) se corren todos, sin excepcion.
_EN_ARTEFACTO = not os.path.isdir(os.path.join(RAIZ, "tools"))

_MODULOS_CON_TOOLS = frozenset({
    "test_cruce_objdb_catalogo.py",
    "test_h4_game_dll.py",
    "test_check_contenido_juego.py",
    "test_parcheo.py",
    "test_probe_unknown_fields.py",
    "test_rdb_names.py",
    "test_recetas.py",
    "test_romfs_img.py",
    "test_scripts_mud.py",
})

if _EN_ARTEFACTO:
    collect_ignore = sorted(_MODULOS_CON_TOOLS)

#: Pruebas que leen ficheros que NO viajan en la release (paginas internas de
#: estado, el mod de regalo y la carpeta `parches/`). Se saltan solo dentro del
#: artefacto; en el arbol de trabajo se corren todas igual.
_SALTAR_EN_ARTEFACTO = (
    "tests/test_estado.py::test_tsv_real_del_repo",
    "tests/test_estado.py::test_check_pasa_en_el_fichero_real_recien_generado",
    "tests/test_parche.py::test_los_parches_del_repo_cargan",
    "tests/test_mod_ejemplo_regalo.py",
)


def pytest_collection_modifyitems(items):
    if not _EN_ARTEFACTO:
        return
    for item in items:
        if any(item.nodeid == n or item.nodeid.startswith(n + "::")
               for n in _SALTAR_EN_ARTEFACTO):
            item.add_marker(pytest.mark.skip(
                reason="fichero que no viaja en la release; se prueba en el repo"))


@pytest.fixture(scope="session", autouse=True)
def _cwd_en_la_raiz():
    """Fija el cwd a la raiz del repo durante toda la sesion de tests."""
    anterior = os.getcwd()
    os.chdir(RAIZ)
    yield RAIZ
    os.chdir(anterior)

