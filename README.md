# ContentReForm

**ContentReForm** is the toolkit — and, later, the platform — for modding the data container of
**Pokémon Pokopia** on native PC. *Content* because that is what it touches (and a nod to
*Content Patcher*, the Stardew Valley mod that made a modding ecosystem possible); *ReForm* because
the game's mission is to rebuild a ruined world. The north: **make any mod, package it, distribute
it, and let somebody else do the same** — the kit is the substrate, the community ecosystem is the
product.

This repository is the **kit**: read, rewrite and mod the data container (game version 2.0.1a,
update build 655360) on a copy of **your own** game files. Python 3.11. Licence
**GPL-3.0-or-later**.

This repository contains **no game content**: no assets, no textures, no models, no text, no
names, no dump, no keys. See [PROCEDENCIA.md](PROCEDENCIA.md) for the provenance of every
figure and the full list of what is deliberately absent.

---

## What this is / what this is not

| This is | This is not |
|---|---|
| A reader and a **writer** for the pair `LD_C0_R.BIN` + `LI_C0_R.IDX`, the data container of the build named above. | A distribution of the game, its data, its assets or its text. Nothing here replaces a copy you must already own. |
| A public **repacker** for that container, verified byte for byte: 12,298 / 12,298 payloads and 0 bytes different on rebuild, with the zlib build declared in `pyproject.toml`. | A decryption or key tool. It never handles a key and never reads an encrypted file. |
| A **declarative mod format**: every edit declares which bytes it expects to find and refuses to apply if they are not there. **`mod.toml` is the native manifest** (the bridge `D-028`, decided 17-nov) and a `mod.json` still loads as **legacy** — same contract, one package, two readers. | An emulator, an online-play tool or anything for multiplayer. There is no networking code in this repository. |
| A save reader/writer for **save version 2.0.1 only**, kept in **maintenance**: it still works for the save version it supports, with its mandatory backup and printed undo command, and it gets no new features. | A general save editor, and not a save editing tool under development. For save editing the living reference is [PokoHex](https://github.com/berichan/PokoHex) (C#, GPL-3.0); this kit's own contribution is the container writer. |
| A library plus a CLI, with the schema kept in data files. | A GUI, and not a stable 1.0 API. **Version 0.7.0.dev0** (the repo used to declare 0.1.0 while 0.5.0 was published; fixed 17-nov), mod format version 1. Interfaces still move until 1.0. |

---

## Supported build

| | |
|---|---|
| Game version | **2.0.1a** |
| Update build | **655360** (RomFS of the update) |
| Entries in `LI_C0_R.IDX` | **12,298** |
| `LD_C0_R.BIN` | **247,317,504 B**, md5 `358a672d506ce2b0399149ede64a6760` |
| `LI_C0_R.IDX` | **393,536 B**, md5 `7e056a097f28a62f002ad961a611edf8` |

Those md5 values are not decoration: a mod declares the md5 of the two files it was written
for, and `pkp` refuses to apply it anywhere else. Run `pkp info` to see the md5 of *your*
files and compare.

**Nothing else has been measured.** Another build may work, or may be silently wrong. If
`pkp repack` reports `IDENTICO` for both files on your build, the writer handles it; if it
reports `DISTINTO`, do not use the writer on it.

---

## 30-second quickstart

```bash
# 1. point the kit at the folder that holds your two container files
#    (optional: the default is ./romfs, relative to where you run pkp)
export PKP_ROMFS="/path/to/your/romfs"      # Windows: set PKP_ROMFS=C:\path\to\romfs

# 2. look at what you have (read-only, nothing is written)
python pkp.py info

# 3. work on a COPY - the kit refuses to write anywhere inside your dump
mkdir -p build/copia
cp "$PKP_ROMFS/LD_C0_R.BIN" "$PKP_ROMFS/LI_C0_R.IDX" build/copia/

# 4. rehearse a mod (default: dry run, no file is opened for writing)
python pkp.py mod apply ejemplos/editar-fila --container build/copia

# 5. apply it for real (writes, keeps a backup, prints the undo command)
python pkp.py mod apply ejemplos/editar-fila --container build/copia --yes
```

Step 2 on the supported build prints, among other things:

```
entradas   : 12298   flags {'0': 4169, '1': 8129}   vacias 2505
payload    : 548327864 B descomprimidos en 246615606 B empaquetados
problemas  : 0
```

**[docs/QUICKSTART.md](docs/QUICKSTART.md)** is the same path written out for someone who has
never seen this repository, including the undo and what to do when a step fails.

---

## Requirements

* **Python 3.11** — `requires-python = ">=3.11,<3.12"`. The test suite is signed on 3.11 and
  refuses to run elsewhere; that is deliberate, not an accident.
* **zlib 1.3.2** (stock build) for the byte-for-byte identity guarantee. With a zlib-ng build
  the recompressed slots come out different; the tool still works, the identity guarantee
  does not apply.
* **Nothing else at runtime**: the CLI and the library are standard library only. The test
  suite needs `pytest`, and the measurement scripts under `tools/` additionally need `PyYAML`.

---

## Environment variables

No path from anyone's machine is built into the code: every default is relative to the working
directory, and each one can be overridden: `PKP_ROMFS`, `PKP_SAVE`, `PKP_PROTECTED`, `PKP_BACKUP_DIR`.
**[docs/COMMANDS.md](docs/COMMANDS.md#environment-variables)** has the four of them with their defaults.

---

## Commands

Every command that writes has `--dry-run` as its **default**, and there is no code path that
writes to your dump.

Global options go before the command (`pkp --container <dir> …`): `--container`, `--json`, and
`--modificado`, which lets the read commands open a **derived** container whose `count` grew past
the declared one (rows added on purpose). Without that flag a drifted `count` is still an error,
as it must be; `version` never drifts. The flag is listed in [docs/COMMANDS.md](docs/COMMANDS.md).

| You want to… | Command |
|---|---|
| see what you have | `pkp info` |
| read a table, or one row | `pkp table <n>` · `pkp row <n> <r>` |
| rebuild the container identical | `pkp repack <outdir>` |
| start a mod | `pkp mod new <name>` · `pkp mod example <dir>` |
| check it before shipping | `pkp mod validate <dir>` |
| package it | `pkp mod pack <dir>` |
| put it in the game | `pkp mod install <dir\|.pkmod> --overlay <store>` |
| see who wins what | `pkp mod status` · `pkp mod doctor` |

**The other 34 commands** — textures, animations, sounds, `.fdata`, the object dictionary, saves —
are in **[docs/COMMANDS.md](docs/COMMANDS.md)**, with their flags.

Add `--json` to any command for machine-readable output.

---

## The mod format in one example

A mod is a folder with a `mod.toml`; a `mod.json` there also loads as **legacy** (D-028), and there
are no scripts to run. Four real ones live in
[`ejemplos/`](ejemplos/), and [MAKE-A-MOD.md](docs/MAKE-A-MOD.md) walks one through from scratch.

```toml
# mod.toml del kit ContentReForm (pkp). Manifiesto adoptado en D-025/D-028.
# Modtopia lee id, version, name, authors, description, game y [[dependencies]]
# e ignora el resto: mt_manifest_parse solo pide las claves que conoce.
id = "ejemplo-editar-fila"
version = "0.1.0"
name = "ejemplo-editar-fila"
# autor: rellénalo a mano; el kit nunca copia tu login del sistema (USER/USERNAME)
authors = ["tu nombre"]
game = ["2.0.1a"]
mod_format = 1
title = "pokopia"
container_md5 = { "LD_C0_R.BIN" = "358a672d506ce2b0399149ede64a6760", "LI_C0_R.IDX" = "7e056a097f28a62f002ad961a611edf8" }

[[edits]]
table = 983
row = 1324
offset = 34
type = "u16"
expect = "2278"
value = "2279"
why = "nameIndex: u16 at +34; the text id is nameIndex + 3"
confidence = "verified"
```

One manifest, one edit, **no game text**. `expect` is the value the author found: if your bytes differ, the
mod refuses to apply — that is how a mod written in May cannot corrupt a save in June. `why` names the
field, or validation flags the edit as a guess. `container_md5` pins the build. Merge is per row and per
offset, never per file, and the same offset in two mods is a declared conflict even when the values
agree. **Uninstall is deleting a folder.**

Every key, type and range: [docs/GLOSSARY.md](docs/GLOSSARY.md) · the contract and what `apply`
guarantees: [docs/MOD-FORMAT.md](docs/MOD-FORMAT.md).

---

## Why it is safe to run

1. **Dry run is the default** for everything that writes. A dry run does not open a single
   file for writing, not even a temporary one.
2. **Writing requires `--container <copy>`.** There is no default, so a write cannot land in
   your dump "by accident", and a path guard rejects the dump tree explicitly.
3. **Writes are atomic**: bytes go to a temporary directory inside the copy, are read back,
   verified against the plan, and only then replace the originals.
4. **Verification before substitution**: the written container re-verifies with 0 problems,
   the only entries that differ are exactly the declared ones, and for text edits the record
   area must stay byte-identical with the same number of slots in the same order.
5. **Backup plus a printed undo command**, every time. `--no-backup` exists and then there is
   no undo — the tool says so instead of pretending otherwise.

---

## Status: what is measured, what is not

**Measured and reproducible**

* Container layout, index records, both entry encodings, block framing, alignment, padding.
* The writer: 12,298 / 12,298 payloads identical on rebuild, and 0 bytes different in
  247,317,504 + 393,536 bytes.
* Geometry of tables `#40`, `#41`, `#42`, `#44`, `#983`, `#4636`–`#4653` (row size, count,
  header, text pool start).
* One field of the 68-byte row of `#983`: `+34 u16`, the text index.
* Text tables: id → block of 6 slots, ordinal addressing, reserialisation that keeps the
  order of slots.
* Save version 2.0.1: header, magic, inventory region (130 records of 5 bytes), the id mask
  (13 bits) and the count byte, on both save pages.

**Not known, and not claimed**

* 15 of the 41 fields mapped in a `#983` row (23 measured, 3 inferred, 15 unknown).
* No confirmed reference from `#983` to the model table `#44`: geometry for a new object
  cannot be created, only existing rows can be re-pointed to existing variants.
* The semantics of the catalogue bitmap in the save (which bit means what).
* Whether the game accepts the result of a mod: nothing here executes the game.

**Not implemented**

* Creating **new entries** in the container, or changing an entry's `blockSize` or `flag`.
* Installing `files[]` payloads (only their shape is checked) and resolving `requires`.
* Any GUI. Any 32-bit/other-platform build. Any other game version.

---

## Documentation

| Document | What it covers |
|---|---|
| [docs/guide/install-mods.md](docs/guide/install-mods.md) | **Two-page quick start:** install a `.pkmod`, set the overlay variable, check with `doctor`, uninstall and verify the original is back. |
| [docs/MAKE-A-MOD.md](docs/MAKE-A-MOD.md) | **Start here to make one:** from your own file to a `.pkmod`, with a generated example mod and the mistakes `validate` names. |
| [docs/INSTALL-AND-DIAGNOSE.md](docs/INSTALL-AND-DIAGNOSE.md) | **Start here to use one:** install, launch with the overlay variable, uninstall, and `doctor`'s causes with their literal messages. |
| [docs/COMMANDS.md](docs/COMMANDS.md) | **Every command and flag**: the 42 `pkp` commands, global options, exit codes and the four environment variables. |
| [docs/GLOSSARY.md](docs/GLOSSARY.md) | Every parameter: container, table geometry, text pool, `mod.toml` keys (and the legacy `mod.json`), CLI flags, save fields. |
| [docs/MOD-FORMAT.md](docs/MOD-FORMAT.md) | The mod contract: manifest, `edits[]`, `text[]` (including the `expect_sha256` criterion), merge, `apply` guarantees, `validate` matrix, exit codes and the four worked examples. |
| [docs/SPEC-CONTAINER.md](docs/SPEC-CONTAINER.md) | Byte-level specification of the container, with test vectors. |
| [docs/SPEC-NAMES.md](docs/SPEC-NAMES.md) | The nine name tables and nine description tables. |
| [patches/README.md](patches/README.md) | The rules for code patches: text-only definitions, `sha256` of the original, build id, expected and new bytes, and the one-command revert. No game content. |
| [PROCEDENCIA.md](PROCEDENCIA.md) | Who made this, from which measurements, under which licence, and what is excluded. |
| [github.com/BananaSoviet/pokopia-data-formats](https://github.com/BananaSoviet/pokopia-data-formats) | The published format specifications (CC BY-SA 4.0). |

`docs/` also holds working notes in Spanish (item-row schema, save regions, architecture,
reports, and the texture, model, animation and audio measurements: `G1T-FORMAT.md`,
`MODELOS-G1M-Y-TEXTURAS-G1T.md`, `ANIMACIONES-G2A.md`, `AUDIO-KTSR.md`, `AUDIO-PROPIO.md`). They are
kept in the repository for continuity and are not part of the documented interface; only the
documents in the table above travel in the release.

---

## Roadmap

**Where 1.0 is (signed 17-nov):** the author tools (**F21**: `validate`, `pack`, `doctor`, `unpack`,
tested against the Modtopia/Recompia loader, not against a fork) plus the **declarative data contract**
(**F19**: `set` / `add` / `copy` addressed by table + row + offset + type, conflicts are an error, not
a silent last-wins). Eleven milestones, four of them need the game running. `docs/PLAN-1.0.md`.

What is already in the tree and was listed here as future: the writer, the manifest, `mod install` /
`mod uninstall` / `mod status` / `mod doctor` (see the command table above).

Still not on the roadmap: a general save editor (maintenance only, PokoHex is the living reference),
a GUI, and generic merge beyond per-row, per-offset composition — guessing at a conflict is worse than
refusing it.

---

## Licence, provenance and credits

* **Code and documentation in this repository: GPL-3.0-or-later.** Full text in
  [LICENSE](LICENSE). GPL-3 is not the default here by accident: the index record layout was
  cross-checked against a GPL-3.0 reader, so the conservative choice is to inherit the
  licence rather than argue about it. Details in [PROCEDENCIA.md](PROCEDENCIA.md).
* **The format specifications are also published separately** under CC BY-SA 4.0 in
  `pokopia-data-formats`. This repository links them; it does not re-license them.
* **Credits:** the reader that first showed this container's index layout is
  [PokoHex](https://github.com/berichan/PokoHex) by *berichan* (C#, GPL-3.0). Its author
  reviewed our findings, reproduced them, and asked for exactly the split this repository
  implements: the save editor upstream, the container repacker and its documentation in a
  separate project. The issue is
  [PokoHex#1](https://github.com/berichan/PokoHex/issues/1).
* **No affiliation.** "Pokémon" and "Pokopia" are trademarks of Nintendo / Creatures Inc. /
  GAME FREAK inc. This project is not affiliated with, endorsed by or sponsored by any of
  them.
* **AI assistance, declared.** This toolkit was written with AI assistance under the
  direction and responsibility of its author. Every figure published here was produced by
  re-running a command, and the corrections that followed are recorded rather than quietly
  edited — that is the only reason to trust a number in this repository.

## No game content, ever

This repository documents **format**, not content. Examples and tests are expressed as table
index, row, offset and id (`#983`, row 1324, `+34`). There is no asset, no string from the
game, no dump and no key anywhere in the tree or in its history. If you ever find game
content here, that is a bug: open an issue and it will be removed.
