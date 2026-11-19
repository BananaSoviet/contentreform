"""F19-C3 · `add` y `copy`: fila nueva al final y texto propio con id nuevo.

Modulo nuevo a proposito: `manifest.py` lo toca otra tarjeta (M0). Aqui viven los
datos, el parseo de las dos claves nuevas, su validacion contra el contenedor y
la construccion del payload derivado. `apply.py` orquesta; `manifest.py` solo
llama a estas funciones.

Geometria (sin inventar nada):

* `add` inserta la fila en `header + count*stride`, escribe `count+1` en +0 y
  deja el `version` intacto (docs/AÑADIR-FILAS.md §2, medido en #983 y #41).
* `copy` clona el bloque de 6 slots del id fuente en el id nuevo de **todas**
  las tablas de nombres declaradas (SPEC F19 §3.5), inserta un registro de 32 B
  clon del ultimo y deja el pool a la misma distancia del final de registros
  (SPEC-NAMES §11.2). Los idiomas no declarados se quedan vacios (§3.6).
* `r = nameIndex + 3` (SPEC-NAMES §6.3): el campo guarda `new_id - 3`.

El texto del juego nunca se escribe en el manifiesto ni en un fichero: el bloque
fuente se lee del contenedor en memoria y solo se sobrescriben los slots que el
autor declara con su propio texto.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

from .. import tables
from . import types as mt
from .errors import ModError, Report

#: Solo enteros no negativos; se usa en el parseo de las claves nuevas.
CONFIDENCES = ("verified", "inference", "guess")


@dataclass
class SetValue:
    """Una celda de la fila nueva, relativa al inicio de la fila."""

    offset: int
    type: str
    value: str
    expect: str = ""
    why: str = ""
    confidence: str = "verified"
    note: str = ""
    index: int = 0

    def where(self) -> str:
        return "add.set[%d] +%d %s" % (self.index, self.offset, self.type)


@dataclass
class Add:
    """Una fila nueva al final de una tabla, clonando otra o en ceros."""

    table: int
    copy_from: int | None
    set: list[SetValue] = field(default_factory=list)
    why: str = ""
    index: int = 0

    @property
    def row(self) -> int:
        spec = tables.get(self.table)
        return spec.count if spec else -1

    def where(self) -> str:
        return "add[%d] #%d fila %d" % (self.index, self.table, self.row)


@dataclass
class Copy:
    """Duplica un id de texto y apunta a el la fila nueva de `add`."""

    table: int
    row: int
    source_id: int
    new_id: int
    langs: list[str]
    offset: int = 34
    type: str = "u16"
    singular: str = ""
    plural: str = ""
    why: str = ""
    index: int = 0

    def where(self) -> str:
        return "copy[%d] #%d fila %d id %d->%d" % (
            self.index, self.table, self.row, self.source_id, self.new_id)


# --------------------------------------------------------------------------
# Parseo (errores al Report, igual que el resto del manifiesto)
# --------------------------------------------------------------------------

def _int(raw: dict, key: str, rep: Report, where: str, *, required=True) -> int:
    if key not in raw:
        if required:
            rep.error("schema.%s" % key, "falta %r" % key, where)
        return 0
    value = raw[key]
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        rep.error("schema.type", "%s debe ser entero >= 0, es %r" % (key, value), where)
        return 0
    return value


def _why(raw: dict, rep: Report, where: str) -> str:
    value = raw.get("why", "")
    if not isinstance(value, str) or not value.strip():
        rep.error("schema.why", "'why' es obligatorio y no puede estar vacio", where)
        return ""
    return value


def _common(raw: dict, rep: Report, where: str) -> tuple[str, str]:
    confidence = raw.get("confidence", "verified")
    if confidence not in CONFIDENCES:
        rep.error("schema.confidence", "'confidence' debe ser uno de %s, es %r"
                  % (", ".join(CONFIDENCES), confidence), where)
        confidence = "guess"
    note = raw.get("note", "")
    if note and not isinstance(note, str):
        rep.error("schema.note", "'note' debe ser cadena", where)
        note = ""
    return confidence, note


def parse_adds(doc: dict, rep: Report) -> list[Add]:
    raws = doc.get("add", [])
    if not isinstance(raws, list):
        rep.error("schema.add", "'add' debe ser una lista")
        return []
    out: list[Add] = []
    for i, raw in enumerate(raws):
        where = "add[%d]" % i
        if not isinstance(raw, dict):
            rep.error("schema.add", "debe ser un objeto", where)
            continue
        table = _int(raw, "table", rep, where)
        copy_from = raw.get("copy_from")
        if copy_from is not None and (isinstance(copy_from, bool)
                                      or not isinstance(copy_from, int) or copy_from < 0):
            rep.error("schema.add.copy_from", "'copy_from' debe ser entero >= 0", where)
            copy_from = None
        why = _why(raw, rep, where)
        sets: list[SetValue] = []
        set_raws = raw.get("set", [])
        if not isinstance(set_raws, list):
            rep.error("schema.add.set", "'set' debe ser una lista", where)
        else:
            for j, item in enumerate(set_raws):
                sw = "%s.set[%d]" % (where, j)
                if not isinstance(item, dict):
                    rep.error("schema.add.set", "debe ser un objeto", sw)
                    continue
                offset = _int(item, "offset", rep, sw)
                typ = item.get("type")
                if not isinstance(typ, str) or typ not in mt.TYPES:
                    rep.error("schema.type", "'type' debe ser uno de %s, es %r"
                              % (", ".join(mt.TYPES), typ), sw)
                    continue
                if "value" not in item:
                    rep.error("schema.value", "falta 'value'", sw)
                    continue
                try:
                    mt.encode(typ, item["value"])
                    expect = item.get("expect", "")
                    if expect != "":
                        mt.encode(typ, expect)
                except mt.TypeError_ as exc:
                    rep.error("schema.value", str(exc), sw)
                    continue
                swhy = item.get("why", why)
                if not isinstance(swhy, str) or not swhy.strip():
                    rep.error("schema.why", "'why' es obligatorio en add.set", sw)
                    swhy = ""
                conf, note = _common(item, rep, sw)
                sets.append(SetValue(offset=offset, type=typ,
                                     value=item["value"] if isinstance(item["value"], str)
                                     else str(item["value"]),
                                     expect=expect if isinstance(expect, str) else str(expect),
                                     why=swhy, confidence=conf, note=note, index=j))
        out.append(Add(table=table, copy_from=copy_from, set=sets,
                       why=why, index=i))
    return out


def parse_copies(doc: dict, rep: Report) -> list[Copy]:
    raws = doc.get("copy", [])
    if not isinstance(raws, list):
        rep.error("schema.copy", "'copy' debe ser una lista")
        return []
    out: list[Copy] = []
    for i, raw in enumerate(raws):
        where = "copy[%d]" % i
        if not isinstance(raw, dict):
            rep.error("schema.copy", "debe ser un objeto", where)
            continue
        table = _int(raw, "table", rep, where)
        row = _int(raw, "row", rep, where)
        source_id = _int(raw, "source_id", rep, where)
        new_id = _int(raw, "new_id", rep, where)
        langs = raw.get("langs")
        if (not isinstance(langs, list) or not langs
                or not all(isinstance(x, str) and x for x in langs)):
            rep.error("schema.copy.langs", "'langs' debe ser una lista de idiomas", where)
            langs = []
        offset = raw.get("offset", 34)
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            rep.error("schema.copy.offset", "'offset' debe ser entero >= 0", where)
            offset = 34
        typ = raw.get("type", "u16")
        if not isinstance(typ, str) or typ not in mt.TYPES:
            rep.error("schema.type", "'type' debe ser uno de %s, es %r"
                      % (", ".join(mt.TYPES), typ), where)
            typ = "u16"
        singular = raw.get("singular", "")
        plural = raw.get("plural", "")
        for key, value in (("singular", singular), ("plural", plural)):
            if not isinstance(value, str) or "\x00" in value:
                rep.error("schema.copy.%s" % key,
                          "'%s' debe ser cadena sin NUL" % key, where)
                if key == "singular":
                    singular = ""
                else:
                    plural = ""
        why = _why(raw, rep, where)
        out.append(Copy(table=table, row=row, source_id=source_id, new_id=new_id,
                        langs=list(langs), offset=offset, type=typ,
                        singular=singular, plural=plural, why=why, index=i))
    return out


# --------------------------------------------------------------------------
# Validacion contra el contenedor (payload ya descomprimido, solo lectura)
# --------------------------------------------------------------------------

def validate_adds(adds: list[Add], view, rep: Report) -> None:
    for add in adds:
        spec = tables.get(add.table)
        if spec is None:
            rep.error("schema.add.table", "la tabla #%d no tiene geometria declarada"
                      % add.table, add.where())
            continue
        if spec.kind != "records":
            rep.error("schema.add.table", "la tabla #%d no es de registros" % add.table,
                      add.where())
            continue
        if add.copy_from is not None:
            if add.copy_from >= spec.count:
                rep.error("schema.add.copy_from",
                          "copy_from %d fuera de rango (0..%d) de #%d"
                          % (add.copy_from, spec.count - 1, add.table), add.where())
                continue
            src = tables.read_row(spec, view.payload(add.table), add.copy_from)
        else:
            src = b"\x00" * spec.stride
        for s in add.set:
            size = mt.type_size(s.type)
            if size is None:
                size = len(mt.encode(s.type, s.value))
            if s.offset + size > spec.stride:
                rep.error("schema.range", "+%d + %d B se sale del stride de %d B de #%d"
                          % (s.offset, size, spec.stride, add.table), s.where())
                continue
            if s.expect and mt.encode(s.type, s.expect) != src[s.offset:s.offset + size]:
                rep.error("mod.expect", "esperaba %s en la fila origen y encontre %s"
                          % (mt.describe(s.type, mt.encode(s.type, s.expect)),
                             mt.describe(s.type, src[s.offset:s.offset + size])),
                          s.where())


def validate_copies(copies: list[Copy], adds: list[Add], view, rep: Report,
                    text_tables: dict[str, int]) -> None:
    finales = {(a.table, a.row) for a in adds if tables.get(a.table) is not None}
    for copy in copies:
        if (copy.table, copy.row) not in finales:
            rep.error("schema.copy.add",
                      "no hay un `add` para la fila %d de #%d: `copy` solo apunta a "
                      "filas nuevas" % (copy.row, copy.table), copy.where())
            continue
        spec = tables.get(copy.table)
        if spec is None or spec.kind != "records":
            continue
        try:
            new_field = mt.encode(copy.type, copy.new_id - 3)
        except mt.TypeError_ as exc:
            rep.error("schema.copy.new_id",
                      "new_id %d no cabe en %s en +%d: %s"
                      % (copy.new_id, copy.type, copy.offset, exc), copy.where())
            continue
        if copy.offset + len(new_field) > spec.stride:
            rep.error("schema.copy.offset", "+%d + %d B se sale del stride de #%d"
                      % (copy.offset, len(new_field), spec.stride), copy.where())
        for lang, idx in sorted(text_tables.items()):
            tspec = tables.get(idx)
            if tspec is None or tspec.kind != "text":
                rep.error("schema.copy.langs",
                          "el idioma %r apunta a #%d sin geometria de texto"
                          % (lang, idx), copy.where())
                continue
            blob = view.payload(idx)
            count, _ = tables.check_header(tspec, blob, modificado=True)
            current = tables.con_conteo(tspec, count)
            derived = tables.con_conteo(tspec, count + 1)
            slots, _ = tables.parse_pool(current, blob)
            try:
                source = tables.block_slots(current, slots, copy.source_id)
                ordinal = tables.slot_ordinal(derived, copy.new_id, 0)
            except tables.TableError as exc:
                rep.error("schema.copy.id", str(exc), copy.where())
                continue
            if not source and lang in copy.langs:
                rep.error("schema.copy.id",
                          "el id fuente %d no tiene bloque en #%d (%s)"
                          % (copy.source_id, idx, lang), copy.where())
            if ordinal >= len(slots):
                rep.error("schema.copy.id",
                          "el id nuevo %d no cabe en el pool de #%d (%s): slots %d, "
                          "primero libre %d" % (copy.new_id, idx, lang,
                                                len(slots), ordinal), copy.where())
                continue
            ocupados = [k for k in range(ordinal, min(ordinal + 6, len(slots)))
                        if slots[k]]
            if ocupados:
                rep.error("schema.copy.id",
                          "el id %d ya tiene texto en #%d (%s): slots %s"
                          % (copy.new_id, idx, lang, ocupados[:6]), copy.where())
            if lang not in copy.langs:
                continue
        for lang in copy.langs:
            if lang not in text_tables:
                rep.error("schema.copy.langs",
                          "el idioma %r no tiene tabla de nombres declarada" % lang,
                          copy.where())


# --------------------------------------------------------------------------
# Construccion (buffers en memoria; nunca escribe disco)
# --------------------------------------------------------------------------

def apply_sets(row: bytes, sets: list[SetValue]) -> tuple[bytes, list[tuple[int, bytes, bytes]]]:
    """Aplica los `set` de un `add` sobre la fila clonada (o sobre ceros)."""
    buf = bytearray(row)
    changes: list[tuple[int, bytes, bytes]] = []
    for s in sets:
        size = mt.type_size(s.type)
        if size is None:
            size = len(mt.encode(s.type, s.value))
        if s.offset + size > len(buf):
            raise ModError("+%d + %d B fuera de la fila de %d B"
                           % (s.offset, size, len(buf)), code="mod.range", where=s.where())
        old = bytes(buf[s.offset:s.offset + size])
        if s.expect and mt.encode(s.type, s.expect) != old:
            raise ModError("esperaba %s en la fila origen y encontre %s"
                           % (mt.describe(s.type, mt.encode(s.type, s.expect)),
                              mt.describe(s.type, old)), code="mod.expect", where=s.where())
        new = mt.encode(s.type, s.value)
        buf[s.offset:s.offset + size] = new
        changes.append((s.offset, old, new))
    return bytes(buf), changes


def new_text_payload(spec, blob: bytes, source_id: int, new_id: int,
                     *, singular: str = "", plural: str = "",
                     declared: bool = True) -> tuple[bytes, set[int]]:
    """Payload de una tabla de nombres con el id nuevo clonado del fuente.

    Devuelve `(payload, ordinales_de_slot_copiados)`. Funciona encadenado: lee el
    `count` del header, asi que dos `copy` sobre la misma tabla suman dos filas.
    """
    count, _ = struct.unpack_from("<II", blob, 0)
    stride = spec.stride or 32
    current = tables.con_conteo(spec, count)
    derived = tables.con_conteo(spec, count + 1)
    records_end = spec.header + count * stride
    slots, terminated = tables.parse_pool(current, blob)
    source = tables.block_slots(current, slots, source_id)
    ordinal = tables.slot_ordinal(derived, new_id, 0)
    if ordinal >= len(slots):
        raise ModError("el id nuevo %d no cabe en el pool de #%d"
                       % (new_id, spec.index), code="mod.text.range")
    touched: set[int] = set()
    if declared:
        for k in range(6):
            at = ordinal + k
            if at >= len(slots):
                break
            slots[at] = source[k] if k < len(source) else b""
            touched.add(at)
    if declared and singular:
        slots[ordinal] = singular.encode("utf-8")
    if declared and plural and ordinal + 2 < len(slots):
        slots[ordinal + 2] = plural.encode("utf-8")
    new_pool = tables.build_pool(slots, terminated)
    ultimo = blob[records_end - stride:records_end]
    separador = blob[records_end:current.pool_start]
    out = bytearray(blob[:records_end]) + bytearray(ultimo) \
        + bytearray(separador) + bytearray(new_pool)
    struct.pack_into("<I", out, 0, count + 1)
    start = derived.pool_start
    if len(out) - start != len(new_pool):
        raise ModError("#%d: el pool derivado no cuadra (%d B vs %d B)"
                       % (spec.index, len(out) - start, len(new_pool)),
                       code="mod.text.geometry")
    out[start:] = new_pool
    return bytes(out), touched
