# Changelog

Notable changes to ContentReForm. A release is immutable: a correction supersedes
the release it fixes instead of editing it. The version comes from
`pokopia.__version__`, the single source of truth for `pkp --version`.

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
