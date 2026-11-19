"""F19-C3: `add` (fila nueva) y `copy` (texto propio con id nuevo).

Los tests usan contenedores sinteticos: ninguna ruta del dump, ningun nombre del
juego. La demostracion contra el dump esta en `informes/m3-add-copy/`.
"""

from __future__ import annotations

import os
import struct

import pytest

from pokopia import nombres, paths, tables
from pokopia.container import compare_payloads, unpack_entry, read_container
from pokopia.mod import apply_mod, load_mod, merge_mods, validate

from tests import helpers


@pytest.fixture()
def mundo(tmp_path, monkeypatch):
    """Tabla de registros con `nameIndex` y tabla de texto con un bloque fuente."""
    with helpers.records_spec():
        with helpers.temp_spec(
            helpers.TEXT_TABLE, kind="text", header=64, stride=32,
            count=helpers.TEXT_COUNT, version=2,
            pool_start=64 + 32 * helpers.TEXT_COUNT,
            language="es", confidence="verified", source="tests",
        ):
            fila = bytearray(b"\x11" * helpers.REC_STRIDE)
            struct.pack_into("<H", fila, 34, 1)      # r = 1 + 3 = 4
            rec = helpers.records_payload({1: bytes(fila)})
            slots = [b""] * helpers.TEXT_SLOTS
            slots[0], slots[1], slots[2] = b"ORIG", b"ORIG-1", b"ORIG-PL"
            cont = helpers.make_container(
                str(tmp_path / "copia"),
                {helpers.REC_TABLE: rec, helpers.TEXT_TABLE: helpers.text_payload(slots)})
            monkeypatch.setattr(nombres, "TEXT_TABLES", {"es": helpers.TEXT_TABLE})
            yield cont, bytes(fila), slots


def _doc(mundo, **cambios):
    cont, _, _ = mundo
    doc = helpers.base_doc(cont, "m3-add-copy")
    doc.update(cambios)
    return doc


def _guardar(doc, tmp_path):
    ruta = helpers.write_mod(str(tmp_path / "mods" / doc["name"]), doc)
    return os.path.dirname(ruta)


def _payload(cont, tabla):
    entries, data = read_container(cont.idx, cont.bin)
    return unpack_entry(data, entries[tabla], index=tabla)


def test_manifiesto_acepta_add_y_copy(mundo, tmp_path):
    cont, _, _ = mundo
    doc = _doc(mundo, add=[{"table": helpers.REC_TABLE, "copy_from": 1,
                            "set": [{"offset": 0, "type": "u32", "value": "7"}],
                            "why": "nueva fila"}],
               copy=[{"table": helpers.REC_TABLE, "row": helpers.REC_COUNT,
                      "source_id": 4, "new_id": 5, "langs": ["es"],
                      "singular": "M3", "why": "texto propio"}])
    mod = load_mod(_guardar(doc, tmp_path))
    assert not [i for i in mod.report.issues if "desconocida" in i.message]
    assert len(mod.adds) == 1 and mod.adds[0].copy_from == 1
    assert mod.adds[0].set[0].offset == 0
    assert len(mod.copies) == 1 and mod.copies[0].new_id == 5
    assert mod.copies[0].langs == ["es"]


def test_add_clona_fila_y_sube_count(mundo, tmp_path):
    cont, fila, _ = mundo
    doc = _doc(mundo, add=[{"table": helpers.REC_TABLE, "copy_from": 1,
                            "set": [{"offset": 0, "type": "u32", "expect": "286331153",
                                     "value": "99"}], "why": "clon con id propio"}])
    mod = load_mod(_guardar(doc, tmp_path))
    assert validate(mod, cont).ok
    res = apply_mod(mod, cont.dir, write=True, keep_backup=False)
    assert res["ok"], res["issues"]

    antes = helpers.records_payload({1: fila})
    despues = _payload(cont, helpers.REC_TABLE)
    assert struct.unpack_from("<II", despues, 0) == (helpers.REC_COUNT + 1, 0)
    assert len(despues) == len(antes) + helpers.REC_STRIDE
    assert despues[4:len(antes)] == antes[4:]
    nueva = despues[len(antes):]
    assert nueva[:4] == struct.pack("<I", 99)
    assert nueva[4:34] == fila[4:34] and nueva[36:] == fila[36:]


def test_add_sin_copy_from_escribe_ceros(mundo, tmp_path):
    cont, _, _ = mundo
    doc = _doc(mundo, add=[{"table": helpers.REC_TABLE,
                            "set": [{"offset": 0, "type": "u8", "value": "7"}],
                            "why": "fila vacia con una celda"}])
    mod = load_mod(_guardar(doc, tmp_path))
    res = apply_mod(mod, cont.dir, write=True, keep_backup=False)
    assert res["ok"], res["issues"]
    nueva = _payload(cont, helpers.REC_TABLE)[64 + helpers.REC_COUNT * helpers.REC_STRIDE:]
    assert nueva == b"\x07" + b"\x00" * (helpers.REC_STRIDE - 1)


def test_add_rechaza_copy_from_fuera_de_rango(mundo, tmp_path):
    cont, _, _ = mundo
    doc = _doc(mundo, add=[{"table": helpers.REC_TABLE, "copy_from": 999,
                            "why": "fuera de rango"}])
    mod = load_mod(_guardar(doc, tmp_path))
    res = apply_mod(mod, cont.dir, write=True, keep_backup=False)
    assert not res["ok"]
    assert any("copy_from" in i["message"] for i in res["issues"])


def _doc_copy(mundo, **cambios):
    base = {"table": helpers.REC_TABLE, "row": helpers.REC_COUNT,
            "source_id": 4, "new_id": 5, "langs": ["es"],
            "singular": "M3-NUEVO", "plural": "M3-PLURALES", "why": "texto propio"}
    base.update(cambios)
    return _doc(mundo,
                add=[{"table": helpers.REC_TABLE, "copy_from": 1, "why": "clon"}],
                copy=[base])


def test_copy_duplica_texto_y_reapunta_nameindex(mundo, tmp_path):
    cont, fila, slots = mundo
    mod = load_mod(_guardar(_doc_copy(mundo), tmp_path))
    assert validate(mod, cont).ok
    res = apply_mod(mod, cont.dir, write=True, keep_backup=False)
    assert res["ok"], res["issues"]

    rec = _payload(cont, helpers.REC_TABLE)
    assert struct.unpack_from("<I", rec, 0)[0] == helpers.REC_COUNT + 1
    assert struct.unpack_from("<II", rec, 0)[1] == 0
    nueva = rec[64 + helpers.REC_COUNT * helpers.REC_STRIDE:]
    assert struct.unpack_from("<H", nueva, 34)[0] == 2       # 5 - 3
    assert nueva[:34] == fila[:34] and nueva[36:] == fila[36:]

    blob = _payload(cont, helpers.TEXT_TABLE)
    spec = tables.con_conteo(tables.get(helpers.TEXT_TABLE), helpers.TEXT_COUNT + 1)
    nuevos, _ = tables.parse_pool(spec, blob)
    assert struct.unpack_from("<I", blob, 0)[0] == helpers.TEXT_COUNT + 1
    assert len(nuevos) == len(slots)
    assert nuevos[6] == b"M3-NUEVO" and nuevos[8] == b"M3-PLURALES"
    assert nuevos[7] == slots[1] and nuevos[12:] == slots[12:]
    assert nuevos[:6] == slots[:6]


def test_copy_no_toca_otras_entradas(mundo, tmp_path):
    cont, _, _ = mundo
    antes_dir = str(tmp_path / "antes")
    os.makedirs(antes_dir, exist_ok=True)
    for name in (paths.BIN_NAME, paths.IDX_NAME):
        with open(os.path.join(cont.dir, name), "rb") as src, \
                open(os.path.join(antes_dir, name), "wb") as dst:
            dst.write(src.read())
    mod = load_mod(_guardar(_doc_copy(mundo), tmp_path))
    assert apply_mod(mod, cont.dir, write=True, keep_backup=False)["ok"]
    comp = compare_payloads(os.path.join(antes_dir, paths.IDX_NAME),
                            os.path.join(antes_dir, paths.BIN_NAME),
                            cont.idx, cont.bin)
    assert comp["errors"] == []
    assert sorted(comp["different"]) == sorted([helpers.REC_TABLE, helpers.TEXT_TABLE])


def test_copy_sube_count_en_todos_los_idiomas(tmp_path, monkeypatch):
    """La spec F19 §3.5: aunque solo se escriba `es`, suben las 9 tablas."""
    langs = ("jp", "es", "de")
    indices = {lang: 60 + i for i, lang in enumerate(langs)}
    specs = []
    payloads = {helpers.REC_TABLE: helpers.records_payload({1: b"\x00" * 68})}
    slots = [b"ORIG" if i < 6 else b"" for i in range(helpers.TEXT_SLOTS)]
    with helpers.records_spec():
        for lang, idx in indices.items():
            specs.append(helpers.temp_spec(idx, kind="text", header=64, stride=32,
                                           count=helpers.TEXT_COUNT, version=2,
                                           pool_start=64 + 32 * helpers.TEXT_COUNT,
                                           language=lang, confidence="verified"))
            specs[-1].__enter__()
            payloads[idx] = helpers.text_payload(slots)
        monkeypatch.setattr(nombres, "TEXT_TABLES", indices)
        try:
            cont = helpers.make_container(str(tmp_path / "copia"), payloads)
            doc = helpers.base_doc(cont, "m3-tres-idiomas")
            doc["add"] = [{"table": helpers.REC_TABLE, "copy_from": 1, "why": "clon"}]
            doc["copy"] = [{"table": helpers.REC_TABLE, "row": helpers.REC_COUNT,
                            "source_id": 4, "new_id": 5, "langs": ["es"],
                            "singular": "M3", "why": "solo español"}]
            mod = load_mod(_guardar(doc, tmp_path))
            res = apply_mod(mod, cont.dir, write=True, keep_backup=False)
            assert res["ok"], res["issues"]
            for idx in indices.values():
                assert struct.unpack_from("<I", _payload(cont, idx), 0)[0] == \
                    helpers.TEXT_COUNT + 1
            for lang, idx in indices.items():
                spec = tables.con_conteo(tables.get(idx), helpers.TEXT_COUNT + 1)
                nuevos, _ = tables.parse_pool(spec, _payload(cont, idx))
                if lang == "es":
                    assert nuevos[6] == b"M3"
                else:
                    assert nuevos[6] == b""
        finally:
            for ctx in specs:
                ctx.__exit__(None, None, None)


def test_copy_y_text_en_la_misma_tabla_no_se_pisan(mundo, tmp_path):
    """`copy` crece la tabla y un `text` posterior edita el id original."""
    cont, _, slots = mundo
    spec = tables.get(helpers.TEXT_TABLE)
    sha = tables.block_sha256(spec, slots, 4)
    doc = _doc_copy(mundo)
    doc["text"] = [{"table": helpers.TEXT_TABLE, "id": 4, "slot": 0,
                    "expect_sha256": sha, "value": "ORIG-NUEVO",
                    "why": "editar el id viejo"}]
    mod = load_mod(_guardar(doc, tmp_path))
    res = apply_mod(mod, cont.dir, write=True, keep_backup=False)
    assert res["ok"], res["issues"]
    blob = _payload(cont, helpers.TEXT_TABLE)
    nuevos, _ = tables.parse_pool(
        tables.con_conteo(spec, helpers.TEXT_COUNT + 1), blob)
    assert nuevos[0] == b"ORIG-NUEVO"
    assert nuevos[6] == b"M3-NUEVO" and nuevos[7] == b"ORIG-1"


def test_merge_no_descarta_add_y_copy(mundo, tmp_path):
    cont, _, _ = mundo
    a = _guardar(_doc_copy(mundo), tmp_path / "a")
    b = _guardar(_doc(mundo, edits=[{"table": helpers.REC_TABLE, "row": 1,
                                     "offset": 0, "type": "u8",
                                     "expect": "17", "value": "18",
                                     "why": "otra celda"}]), tmp_path / "b")
    res = merge_mods(a, b, container_dir=cont.dir, check_container=False)
    assert not res.ok
    assert any("merge.c3" == i.code for i in res.report.issues)


def test_copy_rechaza_id_ya_usado(mundo, tmp_path):
    cont, _, _ = mundo
    mod = load_mod(_guardar(_doc_copy(mundo, new_id=4), tmp_path))
    res = apply_mod(mod, cont.dir, write=True, keep_backup=False)
    assert not res["ok"]
    assert any("id" in i["message"] for i in res["issues"])


def test_copy_exige_add_de_la_fila(mundo, tmp_path):
    cont, _, _ = mundo
    doc = _doc(mundo, copy=[{"table": helpers.REC_TABLE, "row": helpers.REC_COUNT,
                             "source_id": 4, "new_id": 5, "langs": ["es"],
                             "why": "sin add"}])
    mod = load_mod(_guardar(doc, tmp_path))
    res = apply_mod(mod, cont.dir, write=True, keep_backup=False)
    assert not res["ok"]
    assert any("add" in i["message"] for i in res["issues"])
