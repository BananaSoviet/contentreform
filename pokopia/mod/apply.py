"""Aplicacion de un mod a una COPIA del contenedor.

Reglas duras (docs/MOD-FORMAT.md, docs/ARQUITECTURA-KIT.md §5):

* nunca se escribe en el dump original ni en el arbol del emulador;
* `--dry-run` es el modo por defecto: no toca ni un byte en disco;
* con `--yes` se escribe en un directorio temporal y **solo** se sustituye el
  contenedor cuando la relectura con el lector del kit lo confirma;
* con `--keep-backup` (por defecto) se guarda una copia de los dos ficheros y se
  imprime el comando exacto para deshacer.
"""

from __future__ import annotations

import datetime
import hashlib
import os
import shutil
import struct
from dataclasses import dataclass, field

from .. import paths, tables
from ..container import (
    FormatError,
    IndexEntry,
    compare_payloads,
    entry_block_size,
    pack_entry,
    read_container,
    unpack_entry,
    verify,
    write_container,
)
from . import types as mt
from .addcopy import apply_sets, new_text_payload
from .errors import GuardError, ModError, Report
from .manifest import ContainerView, Edit, Mod, TextEdit, text_expect_mismatch, validate

BACKUP_DIR = ".pkp-backup"
TMP_TAG = ".pkp-tmp"
MAX_DIFF_LINES = 500


@dataclass
class Write:
    """Una escritura ya resuelta contra el payload original."""

    kind: str                       # "bytes" | "text"
    table: int
    old: bytes
    new: bytes
    edit: object                    # Edit | TextEdit
    abs_offset: int | None = None   # bytes: offset absoluto en el payload
    slot: int | None = None         # text: ordinal del slot


@dataclass
class Plan:
    mod: Mod
    container: paths.Container
    original: dict[int, bytes] = field(default_factory=dict)
    updated: dict[int, bytes] = field(default_factory=dict)
    writes: list[Write] = field(default_factory=list)
    text_slots: dict[int, tuple[list[bytes], list[bytes], bool]] = field(default_factory=dict)
    # C3: cuantas filas crecio cada tabla, y el contenido exacto de cada fila nueva
    growth: dict[int, int] = field(default_factory=dict)
    expected_rows: dict[int, dict[int, bytes]] = field(default_factory=dict)
    text_copy_slots: dict[int, set[int]] = field(default_factory=dict)


# --------------------------------------------------------------------------
# Plan
# --------------------------------------------------------------------------

def make_plan(mod: Mod, container: paths.Container,
              view: ContainerView | None = None) -> Plan:
    """Resuelve las ediciones sobre los payloads originales (sin escribir nada)."""
    view = view or ContainerView(container)
    plan = Plan(mod=mod, container=container)

    for table in sorted({e.table for e in mod.edits}):
        plan.original[table] = view.payload(table)
    for table in sorted({t.table for t in mod.texts}):
        plan.original[table] = view.payload(table)
    adds = getattr(mod, "adds", [])
    copies = getattr(mod, "copies", [])
    if adds or copies:
        from .. import nombres
        for table in sorted({a.table for a in adds} | {c.table for c in copies}):
            plan.original.setdefault(table, view.payload(table))
        for idx in sorted(set(nombres.TEXT_TABLES.values())):
            plan.original.setdefault(idx, view.payload(idx))

    buffers = {t: bytearray(b) for t, b in plan.original.items()}

    for edit in mod.edits:
        spec = tables.get(edit.table)
        size = mt.type_size(edit.type)
        if size is None:
            size = len(mt.encode(edit.type, edit.value))
        start = (spec.row_offset(edit.row) + edit.offset) if spec else edit.offset
        buf = buffers[edit.table]
        if start + size > len(buf):
            raise ModError("bytes %d..%d fuera del payload de %d B"
                           % (start, start + size, len(buf)),
                           code="mod.range", where=edit.where())
        expected = mt.encode(edit.type, edit.expect)
        found = bytes(buf[start:start + size])
        if found != expected:
            raise ModError("esperaba %s y encontre %s"
                           % (mt.describe(edit.type, expected),
                              mt.describe(edit.type, found)),
                           code="mod.expect", where=edit.where())
        new = mt.encode(edit.type, edit.value)
        buf[start:start + size] = new
        plan.writes.append(Write("bytes", edit.table, found, new, edit,
                                 abs_offset=start))

    # --- C3: filas nuevas (`add`) y texto propio (`copy`) -------------------
    # Se construyen sobre los buffers ya leidos. La fila se añade al final y el
    # header se reescribe con count+1; las tablas de texto crecen igual y el pool
    # se reancla en el nuevo final de registros (docs/AÑADIR-FILAS.md §2-3).
    for add in adds:
        spec = tables.get(add.table)
        if spec is None or spec.kind != "records":
            raise ModError("la tabla #%d no es de registros" % add.table,
                           code="mod.table", where=add.where())
        buf = buffers[add.table]
        pos = spec.header + spec.count * spec.stride
        if add.copy_from is None:
            src = b"\x00" * spec.stride
        else:
            src = bytes(buf[spec.row_offset(add.copy_from):
                            spec.row_offset(add.copy_from) + spec.stride])
            if len(src) != spec.stride:
                raise ModError("la fila origen %d no cabe en #%d"
                               % (add.copy_from, add.table),
                               code="mod.range", where=add.where())
        row, cambios = apply_sets(src, add.set)
        if len(buf) != pos:
            raise ModError("#%d: %d B antes de anadir; esperaba %d B"
                           % (add.table, len(buf), pos),
                           code="mod.geometry", where=add.where())
        buf.extend(row)
        struct.pack_into("<I", buf, 0, spec.count + 1)
        plan.growth[add.table] = plan.growth.get(add.table, 0) + 1
        plan.expected_rows.setdefault(add.table, {})[spec.count] = row
        for off, old, new in cambios:
            plan.writes.append(Write("bytes", add.table, old, new, add,
                                     abs_offset=pos + off))

    for copy in copies:
        from .. import nombres
        spec = tables.get(copy.table)
        if spec is None or spec.kind != "records":
            raise ModError("la tabla #%d no es de registros" % copy.table,
                           code="mod.table", where=copy.where())
        pos = spec.header + copy.row * spec.stride  # la fila nueva está fuera del count declarado
        size = mt.type_size(copy.type) or 2
        new_field = mt.encode(copy.type, copy.new_id - 3)
        buf = buffers[copy.table]
        if pos + copy.offset + size > len(buf):
            raise ModError("nameIndex de la fila nueva fuera del payload de #%d"
                           % copy.table, code="mod.range", where=copy.where())
        old_field = bytes(buf[pos + copy.offset:pos + copy.offset + size])
        buf[pos + copy.offset:pos + copy.offset + size] = new_field
        plan.writes.append(Write("bytes", copy.table, old_field, new_field, copy,
                                 abs_offset=pos + copy.offset))
        plan.expected_rows.setdefault(copy.table, {})[copy.row] = \
            bytes(buf[pos:pos + spec.stride])
        for lang, idx in nombres.TEXT_TABLES.items():
            tspec = tables.get(idx)
            if tspec is None or tspec.kind != "text":
                raise ModError("la tabla de nombres #%d no tiene geometria de texto" % idx,
                               code="mod.table", where=copy.where())
            blob, tocados = new_text_payload(
                tspec, bytes(buffers[idx]), copy.source_id, copy.new_id,
                declared=lang in copy.langs,
                singular=copy.singular if lang in copy.langs else "",
                plural=copy.plural if lang in copy.langs else "")
            buffers[idx] = bytearray(blob)
            plan.growth[idx] = plan.growth.get(idx, 0) + 1
            plan.text_copy_slots.setdefault(idx, set()).update(tocados)

    # --- texto: se VERIFICA contra el payload original y se CONSTRUYE sobre el buffer
    #
    # `expect_sha256` hashea el bloque entero (docs/MOD-FORMAT.md §3.1), y su
    # referencia es el bloque **tal como esta en el contenedor antes del mod** —
    # el que el autor tenia delante al escribir el hash. Compararlo contra el
    # buffer en curso haria que la segunda edicion de un mismo bloque fallara por
    # lo que hizo la primera (y que `validate`, que mira el payload pristino,
    # diera otro veredicto para el mismo mod). Por eso se trocea el pool original
    # una vez y se compara contra esa copia; solo la copia de trabajo se muta.
    pristine: dict[int, tuple[list[bytes], bool]] = {}
    work: dict[int, list[bytes]] = {}
    seen: dict[tuple[int, int, int], TextEdit] = {}
    for text in mod.texts:
        spec = tables.get(text.table)
        if spec is None or spec.kind != "text":
            raise ModError("la tabla #%d no es de texto" % text.table, code="mod.table",
                           where=text.where())
        key = (text.table, text.id, text.slot)
        if key in seen:
            prev = seen[key]
            raise ModError("dos ediciones del mismo slot de texto (%s y %s): declara "
                           "una sola" % (prev.where(), text.where()),
                           code="mod.text.duplicate", where=text.where())
        seen[key] = text
        if text.table not in pristine:
            count0, _ = tables.check_header(spec, plan.original[text.table], modificado=True)
            spec0 = tables.con_conteo(spec, count0)
            slots, terminated = tables.parse_pool(spec0, plan.original[text.table])
            pristine[text.table] = (slots, terminated)
            count_now, _ = tables.check_header(
                spec, bytes(buffers[text.table]), modificado=True)
            spec_now = tables.con_conteo(spec, count_now)
            # el buffer ya puede traer el `copy`: se parte de el para no borrarlo
            work[text.table] = tables.parse_pool(
                spec_now, bytes(buffers[text.table]))[0]
        slots, terminated = pristine[text.table]
        count0, _ = tables.check_header(spec, plan.original[text.table], modificado=True)
        spec0 = tables.con_conteo(spec, count0)
        ordinal = tables.slot_ordinal(spec0, text.id, text.slot)
        if ordinal >= len(slots):
            raise ModError("el slot %d no existe (%d slots)"
                           % (ordinal, len(slots)), code="mod.text.range",
                           where=text.where())
        old = work[text.table][ordinal]      # lo que se sustituye ahora
        message = text_expect_mismatch(text, spec0, slots)   # contra el original
        if message:
            raise ModError(message, code="mod.text.expect", where=text.where())
        new = text.value.encode("utf-8")
        work[text.table][ordinal] = new
        new_pool = tables.build_pool(work[text.table], terminated)
        current_count, _ = tables.check_header(
            spec, bytes(buffers[text.table]), modificado=True)
        pool_start = tables.con_conteo(spec, current_count).pool_start
        buffers[text.table] = bytearray(bytes(buffers[text.table])[:pool_start]
                                        + new_pool)
        plan.writes.append(Write("text", text.table, old, new, text, slot=ordinal))

    plan.updated = {t: bytes(b) for t, b in buffers.items()
                    if bytes(b) != plan.original[t]}
    for table in plan.original:
        spec = tables.get(table)
        if spec is not None and spec.kind == "text" and table in plan.updated:
            c0, _ = tables.check_header(spec, plan.original[table], modificado=True)
            c1, _ = tables.check_header(spec, plan.updated[table], modificado=True)
            old_slots, term = tables.parse_pool(tables.con_conteo(spec, c0),
                                                plan.original[table])
            new_slots, _ = tables.parse_pool(tables.con_conteo(spec, c1),
                                             plan.updated[table])
            plan.text_slots[table] = (old_slots, new_slots, term)
    return plan


# --------------------------------------------------------------------------
# Verificacion
# --------------------------------------------------------------------------

def diff_ranges(old: bytes, new: bytes, limit: int = MAX_DIFF_LINES) -> list[dict]:
    """Tramos contiguos de bytes distintos entre dos payloads del mismo tamano."""
    if len(old) != len(new):
        raise ModError("payload de %d B y %d B: una edicion de bytes no puede cambiar "
                       "el tamano" % (len(old), len(new)), code="mod.verify")
    ranges: list[dict] = []
    start = None
    for i in range(len(old)):
        if old[i] != new[i]:
            if start is None:
                start = i
        elif start is not None:
            ranges.append({"start": start, "end": i, "bytes": i - start})
            start = None
    if start is not None:
        ranges.append({"start": start, "end": len(old), "bytes": len(old) - start})
    out = []
    for r in ranges:
        entries = [{"offset": k, "old": old[k], "new": new[k]}
                   for k in range(r["start"], r["end"])]
        r["detail"] = entries[:limit]
        r["truncated"] = len(entries) > limit
        out.append(r)
    return out


def check_payload_roundtrip(payload: bytes, flag: int, block_size: int) -> bool:
    """Empaqueta y vuelve a descomprimir un payload: el lector recupera lo mismo."""
    packed, _ = pack_entry(payload, flag=flag, block_size=block_size)
    if flag == 0:
        return packed == payload
    header = struct.unpack_from("<III", packed, 0)
    return header[2] == len(payload) and unpack_entry(
        packed, IndexEntry(0, len(payload), len(packed), 1)) == payload


def verify_plan(plan: Plan, view: ContainerView) -> dict:
    """Comprueba en memoria que el resultado contiene solo lo declarado."""
    res = {"tables": {}, "ok": True, "errors": []}
    for table, new_payload in plan.updated.items():
        old_payload = plan.original[table]
        ent = view.entries[table]
        block_size = entry_block_size(view.bin_data, ent)
        info = {"table": table, "old_size": len(old_payload),
                "new_size": len(new_payload), "flag": ent.flag,
                "block_size": block_size}
        growth = plan.growth.get(table, 0)
        comp_old, comp_new = old_payload, new_payload
        comp_diff = comp_new
        spec = tables.get(table)
        if growth:
            if spec is None or spec.stride is None:
                res["ok"] = False
                res["errors"].append("#%d: crecio sin geometria declarada" % table)
                res["tables"][table] = info
                continue
            c0, _ = tables.check_header(spec, old_payload, modificado=True)
            c1, _ = tables.check_header(spec, new_payload, modificado=True)
            info["count_before"], info["count_after"] = c0, c1
            info["growth"] = growth
            if c1 != c0 + growth:
                res["ok"] = False
                res["errors"].append("#%d: count %d -> %d, esperaba +%d"
                                     % (table, c0, c1, growth))
            # Quita las filas insertadas y restaura el count: lo que queda debe
            # cuadrar con el verificador de siempre (solo lo declarado cambia).
            end = spec.header + c0 * spec.stride
            comp_new = new_payload[:end] + new_payload[end + growth * spec.stride:]
            comp_new = old_payload[:4] + comp_new[4:]
            # En tablas de texto el pool puede crecer con el texto nuevo: el
            # verificador byte a byte solo mira cabecera/registros; los slots
            # los comprueba el bloque de abajo.
            comp_diff = comp_new
            if spec.kind == "text" and spec.pool_start is not None:
                comp_diff = comp_new[:spec.pool_start] + comp_old[spec.pool_start:]
            for row, esperada in plan.expected_rows.get(table, {}).items():
                at = spec.header + row * spec.stride
                if new_payload[at:at + spec.stride] != esperada:
                    res["ok"] = False
                    res["errors"].append("#%d: la fila nueva %d no es la declarada"
                                         % (table, row))
        writes = [w for w in plan.writes if w.table == table]
        try:
            info["roundtrip_ok"] = check_payload_roundtrip(
                new_payload, ent.flag, block_size)
        except (FormatError, ValueError) as exc:  # pragma: no cover - defensivo
            info["roundtrip_ok"] = False
            info["roundtrip_error"] = str(exc)

        byte_writes = [w for w in writes if w.kind == "bytes"]
        if byte_writes:
            ranges = diff_ranges(comp_old, comp_diff)
            declared = set()
            for w in byte_writes:
                if w.abs_offset is not None and w.abs_offset < len(comp_old):
                    declared.update(range(w.abs_offset, w.abs_offset + len(w.new)))
            leaked = sorted({k for r in ranges for k in range(r["start"], r["end"])
                             if k not in declared})
            info["diff"] = ranges
            info["diff_bytes"] = sum(r["bytes"] for r in ranges)
            info["outside_declared"] = leaked
            if leaked:
                res["ok"] = False
                res["errors"].append("#%d: %d bytes cambiados fuera de lo declarado "
                                     "(primeros: %s)"
                                     % (table, len(leaked), leaked[:10]))
        text_writes = [w for w in writes if w.kind == "text"]
        copiados = plan.text_copy_slots.get(table, set())
        if text_writes or copiados:
            spec = tables.get(table)
            if spec is None or spec.pool_start is None:
                res["ok"] = False
                res["errors"].append("#%d: edicion de texto sin geometria de texto" % table)
                res["tables"][table] = info
                continue
            slots_old, slots_new, _ = plan.text_slots.get(
                table, (tables.parse_pool(spec, comp_old)[0],
                        tables.parse_pool(spec, comp_new)[0], True))
            prefix_ok = comp_new[:spec.pool_start] == comp_old[:spec.pool_start]
            escritos = {w.slot for w in text_writes}
            changed = [{"slot": i, "old_len": len(a), "new_len": len(b),
                        "old_sha256": hashlib.sha256(a).hexdigest()[:12],
                        # los slots clonados pueden contener texto del juego:
                        # nunca se vuelcan a un informe (norma de contenido)
                        "new": ("<clon del id fuente>" if i in copiados
                                and i not in escritos
                                else b.decode("utf-8", "replace")[:80])}
                       for i, (a, b) in enumerate(zip(slots_old, slots_new)) if a != b]
            info["pool_prefix_identical"] = prefix_ok
            info["slots_changed"] = changed
            info["slots_total"] = [len(slots_old), len(slots_new)]
            expected_slots = {w.slot for w in text_writes} | copiados
            unexpected = {c["slot"] for c in changed} - expected_slots
            if not prefix_ok or len(slots_old) != len(slots_new) or unexpected:
                res["ok"] = False
                res["errors"].append(
                    "#%d: la zona de texto no cuadra (prefijo_identico=%s slots %d->%d "
                    "inesperados=%s)" % (table, prefix_ok, len(slots_old),
                                         len(slots_new), sorted(unexpected)))
        if not info.get("roundtrip_ok", False):
            res["ok"] = False
            res["errors"].append("#%d: el payload reempaquetado no se relee igual" % table)
        res["tables"][table] = info
    return res


# --------------------------------------------------------------------------
# Backup
# --------------------------------------------------------------------------

def make_backup(container: paths.Container, mod: Mod) -> str:
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    root = os.path.join(container.dir, BACKUP_DIR, stamp)
    os.makedirs(root, exist_ok=True)
    for src in (container.bin, container.idx):
        shutil.copy2(src, os.path.join(root, os.path.basename(src)))
    with open(os.path.join(root, "backup.json"), "w", encoding="utf-8") as fh:
        import json
        json.dump({"created": stamp,
                   "mod": mod.name, "mod_version": mod.version,
                   "md5": paths.container_md5(container)}, fh, indent=1)
    return root


def undo_commands(backup: str, container: paths.Container) -> list[str]:
    return ["cp %s %s" % (os.path.join(backup, name),
                          os.path.join(container.dir, name))
            for name in (paths.BIN_NAME, paths.IDX_NAME)]


# --------------------------------------------------------------------------
# Aplicacion
# --------------------------------------------------------------------------

def apply_mod(mod: Mod, container_dir: str | None = None, *, write: bool = False,
              keep_backup: bool = True) -> dict:
    """Aplica `mod`. Sin `write` no toca disco (dry-run). Devuelve el informe.

    La guarda de ruta solo se aplica cuando se va a escribir: un dry-run puede
    leer el dump original (jamás lo abre en escritura).
    """
    container = paths.resolve_container(container_dir)
    protegido = paths.is_protected(container.dir)
    if write:
        try:
            paths.guard_writable(container.dir)
        except PermissionError as exc:
            raise GuardError(str(exc), code="guard", where=container.dir) from None

    result: dict = {
        "mod": mod.name, "mod_version": mod.version, "manifest": mod.manifest,
        "container": container.dir, "dry_run": not write, "written": False,
        "ok": False, "issues": [], "md5_before": {}, "md5_after": {},
        "tables": [], "undo": [], "backup": None, "notes": [],
        "container_protected": protegido,
    }
    if not write and protegido:
        result["notes"].append("contenedor de solo lectura (dump): ensayo, no se "
                               "escribe nunca aqui")
    md5_before = paths.container_md5(container)
    result["md5_before"] = md5_before
    result["md5_after"] = dict(md5_before)

    rep = validate(mod, container)
    if not rep.ok:
        result["issues"] = [i.as_dict() for i in rep.issues]
        result["notes"].append("mod rechazado: %d error(es)" % len(rep.errors))
        return result

    view = ContainerView(container)
    plan = make_plan(mod, container, view=view)
    check = verify_plan(plan, view)
    result["tables"] = [check["tables"][t] for t in sorted(check["tables"])]
    if not check["ok"]:
        result["issues"] = [{"severity": "error", "code": "mod.verify",
                             "message": m, "where": ""} for m in check["errors"]]
        result["notes"].append("verificacion en memoria fallida: no se escribe nada")
        return result

    if not write:
        result["ok"] = True
        result["notes"].append("dry-run: no se ha escrito nada")
        return result

    # --- escritura: temporal, relectura, y solo entonces sustitucion ---------
    tmp_dir = os.path.join(container.dir, TMP_TAG + "-%d" % os.getpid())
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_idx = os.path.join(tmp_dir, paths.IDX_NAME)
    tmp_bin = os.path.join(tmp_dir, paths.BIN_NAME)
    try:
        write_container(container.idx, container.bin, tmp_idx, tmp_bin,
                        replace=plan.updated)
        problems = verify(tmp_idx, tmp_bin, verbose=False)
        if problems["problems"]:
            result["issues"] = [{"severity": "error", "code": "container.verify",
                                 "message": "el contenedor escrito tiene %d problemas: %s"
                                 % (len(problems["problems"]),
                                    problems["problems"][:5]), "where": tmp_dir}]
            result["notes"].append("no se sustituye el destino")
            return result

        comp = compare_payloads(container.idx, container.bin, tmp_idx, tmp_bin)
        edited = sorted(plan.updated)
        unexpected = [i for i in comp["different"] if i not in edited]
        if comp["errors"] or unexpected or comp["different_count"] != len(edited):
            result["issues"] = [{"severity": "error", "code": "mod.verify",
                                 "message": "la relectura no coincide: distintas=%s "
                                            "esperadas=%s inesperadas=%s errores=%s"
                                            % (comp["different"], edited, unexpected,
                                               comp["errors"][:5]), "where": tmp_dir}]
            result["notes"].append("no se sustituye el destino")
            return result

        # comprobacion byte a byte desde disco contra el plan
        new_entries, new_bin = read_container(tmp_idx, tmp_bin)
        disk_ok = True
        for table in edited:
            blob = unpack_entry(new_bin, new_entries[table], index=table)
            if blob != plan.updated[table]:
                disk_ok = False
                result["issues"].append({
                    "severity": "error", "code": "mod.verify",
                    "message": "#%d: el payload leido del contenedor escrito no es el "
                               "planificado" % table, "where": tmp_dir})
        if not disk_ok:
            result["notes"].append("no se sustituye el destino")
            return result

        if keep_backup:
            backup = make_backup(container, mod)
            result["backup"] = backup
            result["undo"] = undo_commands(backup, container)
        os.replace(tmp_bin, container.bin)
        os.replace(tmp_idx, container.idx)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    result["written"] = True
    result["md5_after"] = paths.container_md5(container)
    result["ok"] = True
    result["notes"].append("contenedor sustituido en la copia %s" % container.dir)
    for issue in rep.warnings:
        result["issues"].append(issue.as_dict())
    return result
