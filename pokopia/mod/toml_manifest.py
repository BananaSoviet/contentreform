"""Puente del manifiesto (D-028, camino b): `mod.toml` nativo, `mod.json` legado.

`D-025` adopto el manifiesto de Modtopia y `D-028` decidio el camino (b): el kit
**lee y escribe `mod.toml`** y sigue leyendo `mod.json` como legado. Este modulo
es la mitad de TOML del puente: lee (con `tomllib`, de la biblioteca estandar)
y escribe (un subconjunto pequeno escrito a mano: escalares, tablas en linea y
tablas de arrays), sin dependencias nuevas.

**Dos lectores, un paquete.** `mt_manifest_parse` de Modtopia lee `id`,
`version`, `name`, `authors`, `description`, `game`, `[[dependencies]]`,
`[[settings]]` y `[[hooks."..."]]` y **no rechaza las claves que no conoce**:
solo pide las que conoce (`mt_manifest.c:149-175`, Modtopia 0.6.1 embebido en
Recompia). Por eso el contenido del kit viaja en el mismo fichero y Modtopia lo
ignora sin quejarse.

**Nada aqui es un campo nuevo.** Todos existian en `mod.json`; lo que cambia es
la envoltura, y por eso el mapeo esta escrito una sola vez, aqui:

======================  =============================  =========================
`mod.json` (legado)     `mod.toml` (adoptado)          nota
======================  =============================  =========================
`name`                  `id`                           identificador; ver
                                                       `id_problema`
—                       `name`                         nombre para mostrar de
                                                       Modtopia -> `display_name`
`game.title`            `title`                        raiz; por defecto
                                                       `pokopia` al leer
`game.version`          `game = ["2.0.1a"]`            lista de builds; el kit
                                                       valida contra la primera
`game.container_md5`    `container_md5`                raiz
`requires`              `[[dependencies]]`             id/version/required/order
`mod_format`            `mod_format`                   por defecto `1` al leer
resto (`edits`, `text`, `romfs`, `files`, `merged_from`)
                        igual, como `[[edits]]`...     tablas de arrays
======================  =============================  =========================

Referencia del formato adoptado: `mt_manifest.c` de Recompia v0.14.1
(`runtime/third_party/modtopia/core/src/mt_manifest.c`), Modtopia 0.6.1, MIT.
"""

from __future__ import annotations

import re
import tomllib

from .errors import ModError
from .manifest import MOD_FORMAT

#: Orden fijo de las claves escalares al escribir. Determinista a proposito:
#: `pack` tiene que dar el mismo byte dos veces (M6 de `docs/PLAN-1.0.md`).
ORDEN = ("id", "version", "name", "authors", "description", "game",
         "mod_format", "title", "container_md5")

#: Orden fijo de las tablas de arrays al escribir.
ORDEN_TABLAS = ("edits", "text", "romfs", "files", "dependencies", "merged_from")

#: Cabecera escrita en cada `mod.toml` que genera el kit. Fija, sin fecha ni
#: ruta: forma parte del contenido y por eso no cambia entre ejecuciones.
CABECERA = (
    "# mod.toml del kit ContentReForm (pkp). Manifiesto adoptado en D-025/D-028.\n"
    "# Modtopia lee id, version, name, authors, description, game y [[dependencies]]\n"
    "# e ignora el resto: mt_manifest_parse solo pide las claves que conoce.\n"
)

#: Regla de `id` de Modtopia, literal de `mt_manifest.c:250-261` (`mt_id_valid`):
#: 2-64 caracteres, el primero en minuscula, y solo letras, digitos, `_` y `-`.
#: El kit la aplica a todo `mod.toml`, que es lo que garantiza que el paquete
#: nos lo carga tambien a el.
MT_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")


def es_toml(ruta: str) -> bool:
    """`True` si `ruta` (fichero o `paquete.pkmod!mi-mod.toml`) es TOML."""
    return ruta.lower().endswith(".toml")


def id_problema(ident: str) -> str | None:
    """Motivo por el que `ident` no vale como `id` de Modtopia, o `None`."""
    if MT_ID_RE.match(ident):
        return None
    return ("'id' %r no vale para Modtopia: 2-64 caracteres, empieza por letra "
            "minuscula y solo admite letras, digitos, '_' y '-' (mt_id_valid, "
            "mt_manifest.c:250-261)" % ident)


# -----------------------------------------------------------------------
# Lectura
# -----------------------------------------------------------------------

def _plano(value):
    """`tomllib` devuelve tuplas donde el resto del kit espera listas."""
    if isinstance(value, tuple):
        return [_plano(item) for item in value]
    if isinstance(value, dict):
        return {key: _plano(item) for key, item in value.items()}
    return value


def loads(text: str, where: str = "mod.toml") -> dict:
    """TOML crudo -> documento en crudo (sin mapear). `ModError` si no parsea."""
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ModError("TOML invalido en %s: %s" % (where, exc),
                       code="toml", where=where) from None
    return {key: _plano(value) for key, value in raw.items()}


def _lista(raw: dict, key: str):
    """Valor de `key` como lista; si no lo es, se devuelve tal cual para que
    `parse_mod` emita su propio error de tipo."""
    value = raw.get(key)
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return value


def _builds(value) -> str:
    """`game` de Modtopia (cadena o lista de builds) -> el build del kit.

    El kit valida contra **un** contenedor, asi que se queda con la primera
    build declarada (limite conocido, escrito en `docs/MOD-FORMAT.md` §1).
    """
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return value[0] if value else ""
    return value                      # tipo raro: `_str_field` da el error


def from_toml(raw: dict) -> dict:
    """`mod.toml` crudo -> documento del kit (mismo esquema que `mod.json`).

    El mapeo completo esta en la cabecera de este modulo. `id` ausente o vacio
    deja `name` vacio: es `parse_mod` quien lo reporta como `schema.id`, con el
    nombre del campo que el autor escribio.
    """
    doc: dict = {
        "mod_format": raw.get("mod_format", MOD_FORMAT),
        "name": raw["id"] if isinstance(raw.get("id"), str) else "",
        "authors": _lista(raw, "authors"),
        "requires": _lista(raw, "dependencies"),
        "edits": _lista(raw, "edits"),
        "text": _lista(raw, "text"),
        "romfs": _lista(raw, "romfs"),
        "files": _lista(raw, "files"),
        "merged_from": _lista(raw, "merged_from"),
    }
    if "version" in raw:
        doc["version"] = raw["version"]
    if "description" in raw:
        doc["description"] = raw["description"]
    display = raw.get("name")
    if isinstance(display, str) and display and display != doc["name"]:
        doc["display_name"] = display
    if "game" not in raw:
        doc["game"] = None            # `parse_mod`: "falta 'game' ..."
    else:
        doc["game"] = {
            "title": raw.get("title") or "pokopia",
            "version": _builds(raw["game"]),
            "container_md5": raw.get("container_md5"),
        }
    # Todo lo que no es nuestro se queda tal cual, y aqui no se pierde nada:
    # es lo que hace que la seccion de celdas de F19 (`contract`, `[[set]]`,
    # `[[add]]`) y las claves de Modtopia que el kit no usa (`[[settings]]`,
    # `[[hooks]]`) viajen en el mismo fichero y sobrevivan a un `pack`.
    for key, value in raw.items():
        if key not in _MAPEADAS:
            doc[key] = value
    return doc


#: Claves de `mod.toml` que este modulo traduce; todo lo demas pasa tal cual.
_MAPEADAS = frozenset(("id", "name", "game", "title", "container_md5",
                       "dependencies", "mod_format", "version", "authors",
                       "description", "edits", "text", "romfs", "files",
                       "merged_from"))


# -----------------------------------------------------------------------
# Escritura
# -----------------------------------------------------------------------

def _cadena(value: str) -> str:
    """Cadena TOML entre comillas dobles, con los escapes que exige la spec."""
    out = ['"']
    for char in value:
        code = ord(char)
        if char == '"':
            out.append('\\"')
        elif char == "\\":
            out.append("\\\\")
        elif char == "\n":
            out.append("\\n")
        elif char == "\r":
            out.append("\\r")
        elif char == "\t":
            out.append("\\t")
        elif code < 0x20 or code == 0x7F:
            out.append("\\u%04x" % code)
        else:
            out.append(char)
    out.append('"')
    return "".join(out)


def _clave(key: str) -> str:
    """Clave TOML: desnuda si la admite la spec, entre comillas si no."""
    if re.fullmatch(r"[A-Za-z0-9_-]+", key):
        return key
    return _cadena(str(key))


def _valor(value) -> str:
    """Valor TOML en linea (escalares, listas y tablas en linea)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return _cadena(value)
    if isinstance(value, (list, tuple)):
        return "[%s]" % ", ".join(_valor(item) for item in value)
    if isinstance(value, dict):
        pares = ["%s = %s" % (_clave(str(key)), _valor(item))
                 for key, item in value.items() if item is not None]
        return "{ %s }" % ", ".join(pares) if pares else "{}"
    raise ModError("no se puede escribir %r (%s) en mod.toml"
                   % (value, type(value).__name__), code="schema")


def _es_tablas_de_arrays(value) -> bool:
    """`True` si `value` es una lista no vacia solo de objetos: eso va como
    `[[clave]]`, que es la unica forma TOML de escribirlo sin inventar."""
    return (isinstance(value, (list, tuple)) and bool(value)
            and all(isinstance(item, dict) for item in value))


def _tabla(prefijo: str, item: dict) -> list[str]:
    """Cuerpo de una `[[tabla]]`: escalares primero, luego las anidadas."""
    lineas = ["%s = %s" % (_clave(str(key)), _valor(valor))
              for key, valor in item.items()
              if valor is not None and not _es_tablas_de_arrays(valor)]
    for key, valor in item.items():
        if not _es_tablas_de_arrays(valor):
            continue
        for sub in valor:
            lineas.append("")
            lineas.append("[[%s.%s]]" % (prefijo, _clave(str(key))))
            lineas.extend(_tabla("%s.%s" % (prefijo, _clave(str(key))), sub))
    return lineas


def _a_toml(doc: dict) -> dict:
    """Documento del kit -> documento en la forma de `mod.toml`.

    `game` (objeto del kit) se abre en `game` (lista de builds) + `title` +
    `container_md5`, y `requires` se convierte en `[[dependencies]]`. Las listas
    vacias no se escriben: al leerlas vuelven a ser `[]`, que es lo mismo.
    """
    salida: dict = {}
    juego = doc.get("game")
    if juego is not None and not isinstance(juego, dict):
        raise ModError("'game' debe ser un objeto del kit, es %s"
                       % type(juego).__name__, code="schema")
    ident = doc.get("name") if isinstance(doc.get("name"), str) else ""
    for key, value in doc.items():
        if key in ("game", "requires", "display_name"):
            continue
        if value is None or value == [] or value == {}:
            continue
        salida[key] = value
    # `id` es el `name` del kit; el `name` de Modtopia es el nombre para
    # mostrar, y si no difiere se escribe igual que el `id` (asi lo hace
    # `mt_manifest_parse`, que por defecto pone `name = id`).
    salida["id"] = ident
    salida["name"] = (doc.get("display_name") or ident)
    if isinstance(juego, dict):
        version = juego.get("version")
        if isinstance(version, str) and version:
            salida["game"] = [version]
        title = juego.get("title")
        if isinstance(title, str) and title:
            salida["title"] = title
        md5 = juego.get("container_md5")
        if isinstance(md5, dict) and md5:
            salida["container_md5"] = md5
    requires = doc.get("requires") or []
    if requires:
        salida["dependencies"] = _dependencias(requires)
    return salida


def _dependencias(requires: list) -> list[dict]:
    """`requires` del kit -> `[[dependencies]]` de Modtopia.

    Se mapea en las dos direcciones para que un `[[dependencies]]` escrito a
    mano por un autor de Modtopia sobreviva a un `pack` nuestro. Si alguna
    entrada no tiene `id` no hay forma de escribirla sin inventarlo: se para aqui
    en vez de emitir un fichero que su loader rechazaria.
    """
    salida = []
    for i, item in enumerate(requires):
        if isinstance(item, str):
            salida.append({"id": item})
            continue
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            salida.append({key: value for key, value in item.items()
                           if value is not None})
            continue
        raise ModError("requires[%d] no puede ir a [[dependencies]]: Modtopia "
                       "exige un 'id' de 2-64 caracteres (mt_manifest.c:250-261)"
                       % i, code="schema.requires")
    return salida


def dumps(doc: dict) -> str:
    """Documento del kit -> texto `mod.toml` (terminado en cambio de linea).

    Determinista: mismas claves, mismo orden, mismo texto. Es lo que hace que
    dos `pkp mod pack` seguidos den el mismo sha256.
    """
    ident = doc.get("name")
    if not isinstance(ident, str):
        ident = ""
    problema = id_problema(ident)
    if problema:
        raise ModError("no se puede escribir el mod.toml: %s" % problema,
                       code="schema.id")
    salida = _a_toml(doc)
    claves = list(ORDEN) + sorted(key for key in salida if key not in ORDEN)
    lineas = [CABECERA.rstrip("\n")]
    for key in claves:
        if key not in salida:
            continue
        valor = salida[key]
        if valor is None or _es_tablas_de_arrays(valor):
            continue
        lineas.append("%s = %s" % (_clave(key), _valor(valor)))
    tablas = list(ORDEN_TABLAS) + sorted(key for key in salida
                                         if key not in ORDEN_TABLAS)
    for key in tablas:
        if key not in salida or not _es_tablas_de_arrays(salida[key]):
            continue
        for item in salida[key]:
            lineas.append("")
            lineas.append("[[%s]]" % _clave(key))
            lineas.extend(_tabla(key, item))
    return "\n".join(lineas) + "\n"


def escribir(ruta: str, doc: dict) -> None:
    """Escribe `doc` como `mod.toml` en `ruta` (no crea la carpeta)."""
    with open(ruta, "w", encoding="utf-8") as fh:
        fh.write(dumps(doc))
