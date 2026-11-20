"""F21 §2 · `unpack <paquete.pkmod> [--diff <dump>]`.

Extrae un paquete a una carpeta de trabajo y, si se pide `--dump`, compara cada
celda numérica declarada contra el contenedor base. No hay lector propio: el
contenedor se abre con `ContainerView` (`pokopia.container.read_container` /
`unpack_entry`) y la geometría sale de `pokopia.tables`. El dump **solo se lee**:
`paths.guard_writable()` impide además elegirlo como destino de la extracción.
"""

from __future__ import annotations

import os
import tomllib
import zipfile

from .. import paths, tables
from . import types as mt
from .errors import GuardError, ModError, UsageError
from .manifest import ContainerView
from .overlay import Origen


def _relativa(rel: str) -> str:
    """Normaliza una ruta del paquete y rechaza escapatorios de ZIP."""
    limpia = rel.replace("\\", "/").lstrip("/")
    tramos = limpia.split("/")
    if (not limpia or any(t in ("", ".", "..") for t in tramos)
            or ":" in tramos[0]):
        raise ModError("entrada de paquete insegura: %r" % rel, code="zip")
    return limpia


def _ficheros_de(origen: Origen) -> list[str]:
    if origen.es_paquete:
        with zipfile.ZipFile(origen.ruta) as zf:
            return [_relativa(i.filename) for i in zf.infolist() if not i.is_dir()]
    ficheros: list[str] = []
    for root, _dirs, nombres in os.walk(origen.ruta):
        for nombre in nombres:
            rel = os.path.relpath(os.path.join(root, nombre), origen.ruta)
            ficheros.append(_relativa(rel))
    return sorted(ficheros)


def _campo_de_esquema(leer, tabla: int, field: str) -> dict:
    """Resuelve `field` con `tables/<id>.toml`, si el paquete lo trae.

    F19 §3 permite nombrar campos cuando hay esquema declarado. No hay un
    formato canónico para ese fichero todavía: se aceptan `[[fields]]` y una
    tabla `[fields.<nombre>]`; cualquier otra forma se dice, no se adivina.
    """
    rel = "tables/%d.toml" % tabla
    try:
        datos = leer(rel)
    except KeyError:
        raise ModError("el campo %r exige %s en el paquete" % (field, rel),
                       code="field") from None
    except OSError as exc:
        raise ModError("no se pudo leer %s: %s" % (rel, exc), code="field") from None
    try:
        doc = tomllib.loads(datos.decode("utf-8"))
    except (UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ModError("no se pudo leer %s: %s" % (rel, exc), code="field") from None
    campos = doc.get("fields") or []
    if isinstance(campos, dict):
        encontrado = campos.get(field)
    else:
        encontrado = next((c for c in campos
                           if isinstance(c, dict) and c.get("name") == field), None)
    if not isinstance(encontrado, dict):
        raise ModError("tables/%d.toml no declara el campo %r" % (tabla, field),
                       code="field")
    return encontrado


def _celdas_declaradas(mod, leer) -> list[dict]:
    """Normaliza los dos vocabularios del kit: `[[set]]` (F19) y `edits[]`."""
    celdas: list[dict] = []
    for i, item in enumerate(mod.doc.get("set") or []):
        if not isinstance(item, dict):
            raise ModError("set[%d] debe ser un objeto" % i, code="set")
        celda = {"table": item.get("table"), "row": item.get("row"),
                 "offset": item.get("offset"), "type": item.get("type"),
                 "value": item.get("value"), "where": "set[%d]" % i}
        if "field" in item:
            esquema = _campo_de_esquema(leer, celda["table"], item["field"])
            celda["offset"] = esquema.get("offset")
            celda["type"] = esquema.get("type", celda["type"])
        celdas.append(celda)
    for edit in getattr(mod, "edits", []) or []:
        celdas.append({"table": edit.table, "row": edit.row, "offset": edit.offset,
                       "type": edit.type, "value": edit.value, "where": edit.where()})
    return celdas


def _hex_bytes(raw: bytes) -> str:
    """Hex del valor little-endian, con el ancho del tipo (u16 -> 4 dígitos)."""
    return "0x%0*x" % (len(raw) * 2, int.from_bytes(raw, "little"))


def _diff(celdas: list[dict], view: ContainerView) -> tuple[list[dict], list[str]]:
    cambios: list[dict] = []
    avisos: list[str] = []
    vistas: dict[int, bytes] = {}
    for celda in celdas:
        tabla, fila, offset = celda["table"], celda["row"], celda["offset"]
        where = celda["where"]
        if not all(isinstance(x, int) and not isinstance(x, bool) and x >= 0
                   for x in (tabla, fila, offset)):
            raise ModError("%s: table/row/offset deben ser enteros >= 0" % where,
                           code="celda")
        spec = tables.get(tabla)
        if spec is None:
            avisos.append("%s: la tabla #%d no está en el registro del kit; sin diff"
                          % (where, tabla))
            continue
        typ = celda["type"]
        try:
            size = mt.type_size(typ) if isinstance(typ, str) else None
        except mt.TypeError_ as exc:
            raise ModError("%s: %s" % (where, exc), code="celda") from None
        if size is None:
            avisos.append("%s: tipo %r sin ancho fijo; sin diff" % (where, typ))
            continue
        if fila >= spec.count:
            raise ModError("%s: fila %d fuera de rango (0..%d) de #%d"
                           % (where, fila, spec.count - 1, tabla), code="celda")
        if offset + size > spec.stride:
            raise ModError("%s: +%d + %d B (%s) cruza el stride de %d B de #%d"
                           % (where, offset, size, typ, spec.stride, tabla),
                           code="celda")
        if "value" not in celda:
            raise ModError("%s: falta 'value'" % where, code="celda")
        try:
            nuevo = mt.encode(typ, celda["value"])
        except mt.TypeError_ as exc:
            raise ModError("%s: %s" % (where, exc), code="celda") from None
        if tabla not in vistas:
            blob = view.payload(tabla)
            tables.check_header(spec, blob)
            vistas[tabla] = blob
        blob = vistas[tabla]
        start = spec.row_offset(fila) + offset
        antes = blob[start:start + size]
        if antes == nuevo:
            continue
        cambios.append({
            "celda": "#%d fila %d +%d" % (tabla, fila, offset),
            "antes": _hex_bytes(antes), "despues": _hex_bytes(nuevo),
            "where": where,
        })
    return cambios, avisos


def desempaquetar(paquete: str, destino: str | None = None, dump: str | None = None,
                  *, forzar: bool = False) -> dict:
    """Extrae `paquete` y devuelve el informe de celdas (sin imprimir nada)."""
    with Origen(paquete) as origen:
        mod = origen.leer_manifest()
        if mod.report.errors:
            raise ModError("el manifiesto no es válido: %s"
                           % mod.report.errors[0].message, code="manifiesto")

        def leer(rel: str) -> bytes:
            rel = _relativa(rel)
            if origen.es_paquete:
                with zipfile.ZipFile(origen.ruta) as zf:
                    return zf.read(rel)
            with open(os.path.join(origen.ruta, *rel.split("/")), "rb") as fh:
                return fh.read()

        celdas = _celdas_declaradas(mod, leer)
        cont = paths.resolve_container(dump) if dump else None
        view = ContainerView(cont) if cont is not None else None
        cambios, avisos = _diff(celdas, view) if view is not None else ([], [])

        nombre = os.path.basename(mod.name) or origen.nombre
        dest = os.path.abspath(os.path.expanduser(
            destino or os.path.join("build", "pkmod-unpack", nombre)))
        paths.guard_writable(dest)
        if cont is not None:
            normal = paths.norm(dest)
            raiz = paths.norm(cont.dir)
            if normal == raiz or normal.startswith(raiz + os.sep):
                raise GuardError("destino protegido (solo lectura): %s\n"
                                 "  el --diff se abre solo para leer: extrae en otra carpeta"
                                 % dest, code="destino")
        ficheros = _ficheros_de(origen)
        if ficheros and not forzar and os.path.isdir(dest) and os.listdir(dest):
            raise UsageError("%s ya tiene ficheros: usa -o otra carpeta o --forzar"
                             % dest, code="destino")
        os.makedirs(dest, exist_ok=True)
        for rel in ficheros:
            origen.copiar_a(rel, os.path.join(dest, *rel.split("/")))

    return {"paquete": os.path.abspath(paquete), "mod": mod.name,
            "version": mod.version, "destino": dest, "ficheros": len(ficheros),
            "dump": cont.dir if cont is not None else None,
            "declaradas": len(celdas), "diff": cambios, "avisos": avisos}
