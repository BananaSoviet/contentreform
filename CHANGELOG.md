# Changelog

Notable changes to ContentReForm. A release is immutable: a correction supersedes
the release it fixes instead of editing it. The version comes from
`pokopia.__version__`, the single source of truth for `pkp --version`.

## 0.8.0

Not tagged yet. Publishing is a separate D-022 gate.

- **M6 — reproducible `pack`.** Two runs of `pkp mod pack` over the same source
  produce the same sha256 (byte-for-byte identical package).
- **M7 — `doctor` with names.** `pkp mod doctor <package|dir> --dump <path>`
  names the mod and the table/cell it touches (for example `#983 row 63 +67`);
  a clean package reports no fatal findings.
- **M9 — `unpack --diff`.** `pkp mod unpack --diff` extracts a package and lists
  the cells it changes against the player's dump, with before/after values.

Not in this release: **M10** (loading a `.pkmod` in Recompia v0.14.1) and F19.
This release makes no claim that a package loads in Recompia.

## 0.7.0

Not tagged yet. Publishing is a separate D-022 gate.

- **M0 — native `mod.toml` manifest.** `mod.toml` is now the native manifest and
  `mod.json` still loads as legacy: one package, two readers. The format is
  documented in [MOD-FORMAT.md](docs/MOD-FORMAT.md).
- **M5 — `validate` reports real errors.** A cell that crosses the end of a row
  exits with a non-zero code and prints `file:line`; `--json` returns the
  structured result. The corrected package exits 0. Commands:
  [COMMANDS.md](docs/COMMANDS.md).
- Note: 0.6.1 corrected the T10 finding — the game strings found in the shipped
  documentation and tests were removed and a versioned content gate was added.
  That correction is already published; 0.6.1 stays immutable.

## 0.6.1

- Corrected the T10 finding: no game strings in the shipped artifact, plus a
  versioned build gate that fails if they reappear. No new capability.

## 0.6.0

- First release of the kit itself: version, public documentation and the suite
  green in a clean build. No new capability.
