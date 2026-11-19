"""F21 C2 + §2 · `validate` con posición real y salida estructurada.

Añade encima del validador que ya tenía el kit (`manifest.validate`), no lo
reescribe. Dos piezas:

* `LineMap`: traduce el `where` semántico de los informes (`edits[0]`, `id`,
  ...) a `fichero:línea` leyendo el texto del manifiesto. No inventa líneas:
  si no encuentra el sitio devuelve `line=None`.
* `validate_contract`: los ocho chequeos de `docs/SPEC-F21-HERRAMIENTAS-AUTOR.md`
  §2, en ese orden, con un error como máximo por tipo y acumulando entre tipos.

Solo biblioteca estándar (`tomllib`, `os`, `re`). El dump no se toca: la
geometría se compara contra el registro del kit (`pokopia.tables`), no contra
los ficheros del jugador.
"""

from __future__ import annotations

import os
import re
import tomllib

from .. import tables
from . import types as mt
from .errors import Report

#: F19-C5 / SPEC F19 §3: única versión del contrato que conoce el kit.
CONTRACT = "1"
#: Build medido en casa (655360). El kit solo valida contra ese build.
KNOWN_BUILDS = ("2.0.1a",)
#: F19-C1: el contenedor nunca viaja dentro del paquete.
CONTAINER_FILES = ("LD_C0_R.BIN", "LI_C0_R.IDX")
#: SPEC F19 §3: los tipos admitidos en `set` (sin `bytes`, sin `f64`).
SET_TYPES = ("u8", "u16", "u32", "u64", "i8", "i16", "i32", "i64", "f32")
ARRAY_SECTIONS = ("edits", "text", "add", "set", "copy", "romfs", "files",
                  "dependencies", "merged_from")
_HEADER_RE = re.compile(r"^\s*\[\[([A-Za-z0-9_.-]+)\]\]")
_KEY_RE = re.compile(r"^\s*([A-Za-z0-9_-]+)\s*=")
_JSON_KEY_RE = re.compile(r'^\s*"([A-Za-z0-9_.-]+)"\s*:')
_ITEM_RE = re.compile(r"^([A-Za-z0-9_]+)\[(\d+)\](?:\.([A-Za-z0-9_]+)\[(\d+)\])?$")

#: Código del informe -> campo del manifiesto donde suele estar el fallo.
_FIELD_FOR_CODE = {
    "schema.id": "id",
    "schema.name": "name",
    "schema.mod_format": "mod_format",
    "schema.version": "version",
    "schema.authors": "authors",
    "schema.game": "game",
    "schema.game.container_md5": "container_md5",
    "mod.container_md5": "container_md5",
    "schema.type": "type",
    "schema.value": "value",
    "schema.expect": "expect",
    "schema.text.expect": "expect",
    "schema.text.expect_sha256": "expect_sha256",
    "schema.text.value": "value",
    "schema.why": "why",
    "mod.expect": "expect",
    "mod.range": "offset",
    "schema.requires": "requires",
    "schema.edits": "edits",
    "schema.text": "text",
    "schema.add": "add",
}

_FIELD_GEOMETRY = ("header", "count", "stride", "version")


class LineMap:
    """Índice ligero de líneas del manifiesto, para `fichero:línea`.

    `tomllib` no da posiciones y no vamos a añadir un parser de TOML propio:
    basta con reconocer cabeceras `[[sección]]` y claves `clave =` (o su
    equivalente JSON) para decir en qué línea está la entrada culpada.
    """

    def __init__(self, text: str, path: str):
        self.file = os.path.basename(path)
        self.text = text
        self.lines = text.splitlines()
        self.es_toml = path.lower().endswith(".toml")
        self.headers: dict[str, list[int]] = {}
        self.keys: dict[str, int] = {}
        for number, raw in enumerate(self.lines, 1):
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                continue
            head = _HEADER_RE.match(raw)
            if head:
                self.headers.setdefault(head.group(1), []).append(number)
                continue
            key = (_KEY_RE if self.es_toml else _JSON_KEY_RE).match(raw)
            if key:
                self.keys.setdefault(key.group(1), number)

    def _item_line(self, section: str, index: int) -> int | None:
        if self.es_toml:
            found = self.headers.get(section, [])
            return found[index] if 0 <= index < len(found) else (found[0] if found else None)
        # JSON escrito con indentación: la clave de la sección y las llaves
        # de sus objetos. Aproximación deliberada: el legado solo avisa.
        start = self.keys.get(section)
        if start is None:
            return None
        seen = 0
        for number in range(start, len(self.lines) + 1):
            if "{" in self.lines[number - 1]:
                if seen == index:
                    return number
                seen += 1
        return start

    def _field_line(self, start: int, field: str) -> int:
        """Línea de `field` dentro de la entrada que empieza en `start`."""
        patron = (re.compile(r"^\s*%s\s*=" % re.escape(field)) if self.es_toml
                  else re.compile(r'^\s*"%s"\s*:' % re.escape(field)))
        for number in range(start + 1, len(self.lines) + 1):
            raw = self.lines[number - 1]
            if self.es_toml and re.match(r"^\s*\[\[?", raw):
                break
            if not self.es_toml and raw.strip() in ("}", "],", "]"):
                break
            if patron.match(raw):
                return number
        return start

    def place(self, where: str = "", field: str | None = None) -> tuple[str, int | None]:
        """`(fichero, línea)` de `where`; línea `None` si no se sabe."""
        where = (where or "").strip().strip("'\"")
        item = _ITEM_RE.match(where)
        if item:
            section, index, sub, subindex = item.groups()
            start = self._item_line(section, int(index))
            if start is None:
                return self.file, None
            if sub:
                nested = self._item_line("%s.%s" % (section, sub), int(subindex))
                if nested is not None:
                    start = nested
            if field:
                return self.file, self._field_line(start, field)
            return self.file, start
        if where in self.keys:
            line = self.keys[where]
            if field and field != where:
                line = self._field_line(line, field)
            return self.file, line
        if where in self.headers and self.headers[where]:
            return self.file, self.headers[where][0]
        return self.file, None


def annotate(report: Report, line_map: LineMap) -> Report:
    """Pone `file`/`line` a los avisos del validador que ya tenía el kit."""
    for issue in report.issues:
        if issue.file:
            continue
        field = _FIELD_FOR_CODE.get(issue.code)
        if issue.code in ("schema.range", "mod.range") and "fila" in issue.message:
            field = "row"
        file, line = line_map.place(issue.where, field)
        if line is not None:             # sin línea fiable, no fingimos posición
            issue.file, issue.line = file, line
    return report


def _error(report: Report, line_map: LineMap, code: str, message: str,
           where: str = "", field: str | None = None,
           file: str | None = None, line: int | None = None) -> None:
    if file is None:
        file, line = line_map.place(where, field)
    report.error(code, message, where, file=file, line=line)


def _entero(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _tiene_contrato_f19(doc: dict) -> bool:
    """¿El paquete usa la capa declarativa de F19?

    Los paquetes kit-nativos (`edits`, sin `contract`) siguen bajo el validador
    de siempre y por eso no se les exige la clave nueva: `test_mod_toml.py` y
    los ejemplos del repo son de ese tipo y deben seguir dando exit 0.
    """
    if "contract" in doc or "set" in doc:
        return True
    text = doc.get("text", [])
    return (isinstance(text, list) and any(isinstance(item, dict) and "langs" in item
                                           for item in text))


def _check_set(item: object, line_map: LineMap, index: int, report: Report,
               package_dir: str = "") -> bool:
    """Un `[[set]]`. Devuelve True si puso un error (y el tipo se detiene)."""
    where = "set[%d]" % index
    if not isinstance(item, dict):
        _error(report, line_map, "f21.set", "debe ser un objeto", where)
        return True
    table = _entero(item.get("table"))
    row = _entero(item.get("row"))
    offset = _entero(item.get("offset"))
    typ = item.get("type")
    if table is None:
        _error(report, line_map, "f21.set.table", "falta 'table' (entero >= 0)",
               where, field="table")
        return True
    spec = tables.get(table)
    if spec is None:
        _error(report, line_map, "f21.set.table",
               "la tabla #%d no está en el índice del kit" % table, where, field="table")
        return True
    if "field" in item:
        # Un `set` por nombre necesita esquema declarado (F19 §3, regla 2).
        rel = "tables/%d.toml" % table
        if not os.path.isfile(os.path.join(package_dir, "tables", "%d.toml" % table)):
            _error(report, line_map, "f21.set.field",
                   "el campo %r exige %s con su geometría" % (item["field"], rel),
                   where, field="field", file=rel)
            return True
    if row is None or row >= spec.count:
        _error(report, line_map, "f21.set.row",
               "fila %r fuera de rango (0..%d) de la tabla #%d" % (row, spec.count - 1, table),
               where, field="row")
        return True
    if not isinstance(typ, str) or typ not in SET_TYPES:
        _error(report, line_map, "f21.set.type",
               "tipo %r no admitido: %s" % (typ, ", ".join(SET_TYPES)), where, field="type")
        return True
    size = mt.type_size(typ) or 0
    if offset is None:
        _error(report, line_map, "f21.set.offset", "falta 'offset' (entero >= 0)",
               where, field="offset")
        return True
    if offset + size > spec.stride:
        _error(report, line_map, "f21.set.stride",
               "offset %d + %d B (%s) cruza el stride de %d B de la tabla #%d (fila %d)"
               % (offset, size, typ, spec.stride, table, row), where, field="offset")
        return True
    if "value" not in item:
        _error(report, line_map, "f21.set.value", "falta 'value'", where, field="value")
        return True
    try:
        mt.encode(typ, item["value"])
    except mt.TypeError_ as exc:
        _error(report, line_map, "f21.set.value", str(exc), where, field="value")
        return True
    return False


def _check_add(item: object, line_map: LineMap, index: int, report: Report) -> bool:
    where = "add[%d]" % index
    if not isinstance(item, dict):
        _error(report, line_map, "f21.add", "debe ser un objeto", where)
        return True
    table = _entero(item.get("table"))
    if table is None:
        _error(report, line_map, "f21.add.table", "falta 'table' (entero >= 0)",
               where, field="table")
        return True
    spec = tables.get(table)
    if spec is None:
        _error(report, line_map, "f21.add.table",
               "la tabla #%d no está en el índice del kit" % table, where, field="table")
        return True
    copy_from = item.get("copy_from")
    if copy_from is not None:
        origin = _entero(copy_from)
        if origin is None or origin >= spec.count:
            _error(report, line_map, "f21.add.copy_from",
                   "copy_from %r fuera de rango (0..%d) de #%d" % (copy_from, spec.count - 1, table),
                   where, field="copy_from")
            return True
    sets = item.get("set", [])
    if not isinstance(sets, list):
        _error(report, line_map, "f21.add.set", "'set' debe ser una lista", where)
        return True
    for j, cell in enumerate(sets):
        if not isinstance(cell, dict):
            _error(report, line_map, "f21.add.set", "debe ser un objeto",
                   "%s.set[%d]" % (where, j))
            return True
        typ = cell.get("type")
        offset = _entero(cell.get("offset"))
        if not isinstance(typ, str) or typ not in SET_TYPES:
            _error(report, line_map, "f21.add.set.type",
                   "tipo %r no admitido: %s" % (typ, ", ".join(SET_TYPES)),
                   "%s.set[%d]" % (where, j), field="type")
            return True
        size = mt.type_size(typ) or 0
        if offset is None or offset + size > spec.stride:
            _error(report, line_map, "f21.add.set.stride",
                   "offset %r + %d B cruza el stride de %d B de #%d"
                   % (offset, size, spec.stride, table),
                   "%s.set[%d]" % (where, j), field="offset")
            return True
    return False


def _check_text(item: object, line_map: LineMap, index: int, report: Report) -> bool:
    where = "text[%d]" % index
    if not isinstance(item, dict) or "langs" not in item:
        return False                     # texto del kit: ya lo valida parse_mod
    text_id = _entero(item.get("id"))
    if text_id is None:
        _error(report, line_map, "f21.text.id", "falta 'id' (entero >= 0)",
               where, field="id")
        return True
    counts = []
    for i in range(len(tables.NAMES_LANGS)):
        spec = tables.get(4645 + i)      # tablas de nombres, SPEC-NAMES §3.1
        if spec is not None:
            counts.append(spec.count)
    tope = max(counts) + 3 if counts else 3
    primero = getattr(tables, "TEXT_FIRST_ID", 4)
    if not primero <= text_id <= tope:
        _error(report, line_map, "f21.text.id",
               "id %d fuera de rango (%d..%d)" % (text_id, primero, tope), where, field="id")
        return True
    langs = item["langs"]
    if not isinstance(langs, list):
        _error(report, line_map, "f21.text.langs", "'langs' debe ser una lista",
               where, field="langs")
        return True
    desconocidos = [lang for lang in langs
                    if not isinstance(lang, str) or lang not in tables.NAMES_LANGS]
    if desconocidos:
        _error(report, line_map, "f21.text.langs",
               "idiomas no declarados: %s (válidos: %s)"
               % (", ".join(map(str, desconocidos)), ", ".join(tables.NAMES_LANGS)),
               where, field="langs")
        return True
    return False


def _check_contenedor(package_dir: str, report: Report) -> None:
    for root, _dirs, files in os.walk(package_dir):
        for name in files:
            if name in CONTAINER_FILES:
                rel = os.path.relpath(os.path.join(root, name), package_dir).replace("\\", "/")
                report.error("f21.container_en_paquete",
                             "el paquete trae %s: F19-C1 prohíbe empaquetar el contenedor"
                             % rel, file=rel)
                return                   # un error por tipo


def _check_geometria(package_dir: str, report: Report) -> None:
    carpeta = os.path.join(package_dir, "tables")
    if not os.path.isdir(carpeta):
        return
    for name in sorted(os.listdir(carpeta)):
        if not name.endswith(".toml"):
            continue
        ruta = os.path.join(carpeta, name)
        rel = "tables/" + name
        try:
            with open(ruta, "rb") as fh:
                doc = tomllib.load(fh)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            report.error("f21.tables.toml", "%s: %s" % (rel, exc), file=rel)
            return
        ident = doc.get("id", name[:-5])
        try:
            ident = int(ident)
        except (TypeError, ValueError):
            report.error("f21.tables.id", "%s: 'id' no es un entero" % rel, file=rel)
            return
        spec = tables.get(ident)
        if spec is None:
            report.error("f21.tables.id", "%s: la tabla #%d no está en el registro del kit"
                         % (rel, ident), file=rel)
            return
        for campo in _FIELD_GEOMETRY:
            if campo in doc and doc[campo] != getattr(spec, campo):
                report.error("f21.tables.geometria",
                             "%s: %s=%r no cuadra con el registro del kit (%s=%r)"
                             % (rel, campo, doc[campo], campo, getattr(spec, campo)),
                             file=rel)
                return                   # un error por tipo


def validate_contract(mod, line_map: LineMap, package_dir: str) -> Report:
    """Los ocho chequeos de F21 §2, en orden; para en el primero de cada tipo."""
    rep = Report()
    doc = mod.doc
    f19 = _tiene_contrato_f19(doc)

    # 1 · parseo: `load_mod` ya lo hizo; un TOML roto no llega hasta aquí.
    # 2 · contract
    if "contract" in doc:
        if str(doc["contract"]) != CONTRACT:
            _error(rep, line_map, "f21.contract",
                   "contrato %r desconocido: esta versión del kit solo entiende %r"
                   % (doc["contract"], CONTRACT), "contract", field="contract")
    elif f19:
        _error(rep, line_map, "f21.contract", "falta 'contract = \"%s\"'" % CONTRACT,
               "contract")

    # 3 · game / build
    juego = doc.get("game")
    build = juego.get("version") if isinstance(juego, dict) else None
    if f19 and build not in KNOWN_BUILDS:
        _error(rep, line_map, "f21.game",
               "build %r no reconocido (medidos: %s)"
               % (build, ", ".join(KNOWN_BUILDS)), "game", field="game")

    # 4 · set
    sets = doc.get("set", [])
    if isinstance(sets, list):
        for i, item in enumerate(sets):
            if _check_set(item, line_map, i, rep, package_dir):
                break

    # 5 · add
    adds = doc.get("add", [])
    if isinstance(adds, list):
        for i, item in enumerate(adds):
            if _check_add(item, line_map, i, rep):
                break

    # 6 · text
    textos = doc.get("text", [])
    if isinstance(textos, list):
        for i, item in enumerate(textos):
            if _check_text(item, line_map, i, rep):
                break

    # 7 · el paquete no trae el contenedor
    _check_contenedor(package_dir, rep)

    # 8 · geometría declarada en tables/<id>.toml
    _check_geometria(package_dir, rep)
    return rep
