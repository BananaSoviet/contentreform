# Install a mod, uninstall it, and check the result

**A two-page guide for someone who has never opened this repository.** It uses
ContentReForm 0.6.1.dev0. You own a copy of the game; this kit never ships game
files and never repacks the game for you.

Installing means putting a **`.pkmod` package** into a folder the game reads
*before* its `RomFS.img`. Uninstalling means taking that mod's files out and
proving the original file is back. The image itself is never written. `doctor`
checks the whole setup without starting the game.

## Before you start

* `pkp --version` prints `0.6.1.dev0`. If `pkp` is not on your PATH, install the
  `0.6.1.dev0` wheel first.
* You need a `.pkmod` package. If you have not made one yet, see
  [Make a mod](../MAKE-A-MOD.md); to try the flow now, the kit can generate one
  with `pkp mod example my-example-mod` (23 bytes written by the kit, no game
  content). Its payload is **not a valid asset**: walk through the commands,
  but do not launch the game with that example installed.
* You need your `RomFS.img` and your copy of the container (the folder with
  `LD_C0_R.BIN` and `LI_C0_R.IDX`, game 2.0.1a / update 655360). Set
  `PKP_ROMFS` to that folder, or pass `--container <folder>` to every command.
* **Close the game before installing or uninstalling.** The kit refuses while
  the game's runtime is running; it never closes the game for you.
* These examples use the generated package. Replace `my-example-mod` and
  `ejemplo-overlay-0.1.0.pkmod` with your own folder and package name; the
  commands are the same.

```bash
pkp mod validate my-example-mod
pkp mod pack my-example-mod -o packages --img RomFS.img
# package: packages/ejemplo-overlay-0.1.0.pkmod
```

`validate` ends in `resultado: OK (0 errores, 0 avisos)`. `pack` records the
hash of the original file in `RomFS.img` — that record is what lets the
uninstall prove the original came back.

## 1. Install

```bash
pkp mod install packages/ejemplo-overlay-0.1.0.pkmod --overlay mods --img RomFS.img --crear
```

`--crear` is only needed the first time; the store now contains
`mods/mods/ejemplo-overlay/` and `mods/installed.json`. The command prints two
lines you will use next:

```
DM_ROMFS_OVERLAY=.../mods/mods/ejemplo-overlay
relativo al cwd: mods/mods/ejemplo-overlay
```

Nothing was written to `RomFS.img`, and nothing was repacked.

## 2. Point the game at the store, then play

Copy the **relative** line exactly as printed into the shell that starts the
game:

```bash
export DM_ROMFS_OVERLAY=mods/mods/ejemplo-overlay      # sh / bash
```

```bat
set DM_ROMFS_OVERLAY=mods\mods\ejemplo-overlay          :: cmd.exe
```

Start the game from the same folder you ran `pkp` in. On Windows, **never use
an absolute path** here: the game splits the value on `:`, so a drive letter
cuts the path in two. If `install` says no relative form exists (store and
current folder on different drives), follow the store-root instruction it
prints. Now the file your mod declares replaces the game file at the same
path; the rest still comes from `RomFS.img`.

## 3. Check before you play

```bash
pkp mod status --overlay mods --img RomFS.img
pkp mod doctor --overlay mods --img RomFS.img
```

`status` says who serves each path (`sirve: overlay`) and whether any path is
claimed by two mods. `doctor` reads the store, the files and the image and
ends with `resultado: sano (0 fallo(s), 0 aviso(s))` when all is well. Its exit
code is 0 with no `FALLO`; a `FALLO` stops the mod from loading, an `aviso` is
worth reading but does not block. If you see
`mods.sin_conflictos ... lo sirven X e Y (gana X, bytes distintos)`, two mods
cover the same file: the first folder in `DM_ROMFS_OVERLAY` wins. Keep one, or
decide the order deliberately. `doctor` does not launch the game.

## 4. Uninstall and leave everything as it was

Close the game again, then:

```bash
pkp mod uninstall ejemplo-overlay --overlay mods --img RomFS.img
pkp mod doctor --overlay mods --img RomFS.img
```

`uninstall` reports `original restaurado`, then `restaurados: 1  sombreados
por otro mod: 0  sin original: 0` and `resultado: OK`. The second `doctor`
shows `0 mod(s)` and `resultado: sano (0 fallo(s), 0 aviso(s))`. Compare the
hash of `RomFS.img` with the one you took before installing (`sha256sum
RomFS.img`): it must be identical. You can then delete the `mods/` folder;
`doctor`'s `almacen.sin_sobras` check catches folders left behind that the
game would still read.

## If something is wrong

| Message | What to do |
|---|---|
| `no es el que se instalo` | the overlay file changed after installing; install the package again |
| `el img es otro build` | you are using a different `RomFS.img`; use the one the mod was packed against |
| `DM_ROMFS_OVERLAY no esta puesta` | export the exact relative line `install` printed, in the shell that starts the game |
| `lo sirven X e Y` | two mods cover one path; remove one or reorder `DM_ROMFS_OVERLAY` |

## What this guide does not cover

Making a mod, composing two mods, or validating a texture/model/audio asset:
`doctor` checks the *installation*, not whether the game accepts your asset.
Only game 2.0.1a with update 655360 is supported by this kit today. Never
publish a `.pkmod` that carries files copied out of the game.

**Next:** [Make a mod](../MAKE-A-MOD.md) ·
[Install and diagnose — every `doctor` message](../INSTALL-AND-DIAGNOSE.md) ·
[All commands](../COMMANDS.md).
