# Changelog

Release history of the `Jarvis-HEP-Sampler` distribution (import package
`jarvis_hep_sampler`, CLI `jsampler`). Developer documentation lives in
[Jarvis-Books `Docs/Jarvis-HEP-Sampler/`](https://github.com/Pengxuan-Zhu-Phys/Jarvis-Books/blob/main/Docs/Jarvis-HEP-Sampler/README.md).

## 1.1.1 — 2026-10-18

- Exclude maintainer release helpers, local configuration, credentials, and
  generated files from distribution archives. The entire local `research/`
  tree remains untracked and is excluded from distributions.

- The standalone `jhsrel` command now supports read-only `--dry` checks and
  completes a PyPI release with a local editable install, Git tag, and GitHub
  release.
- The README, which is the PyPI project description, matches the published
  version: the install pin and the host-contract note named 1.0.3. Links in it
  are absolute so they work on PyPI.

## 1.1.0 — 2026-10-18

Required by Jarvis-HEP 2.1.0 (host contract 2).

- `HOST_CONTRACT_VERSION = 2` marks the host-facing interface. Plug-in
  `API_VERSION` and the stream protocol stay 1.
- Reserved method names are enforced only where an external plug-in enters:
  `jsampler init`, registry `load` and `check_plugin` call the new
  `check_external_method_name`. `check_method_name` and `parse_metadata` now
  check syntax and structure only; their `reserved_names` and
  `trusted_builtin_method` keywords are removed. Loaders take an optional
  `metadata_validator` hook, run before options schemas and hooks.
- `jsampler check` exits 2 for a reserved name and 1 for algorithm output or
  repeatability failures.
- `jarvis_hep_sampler.cli.main(..., catalog=CatalogExtension(...))` lets a host
  add data to `list` and `info` (`augment_list`, `resolve_info`,
  `list_sections`); parsing, errors and text/JSON rendering stay in the SDK.
  Existing JSON fields are unchanged.
- Documentation moved to Jarvis-Books; the repository keeps only `README.md`
  and `CHANGELOG.md`.

## 1.0.3 — 2026-10-16

- Jarvis-HEP's built-in and shipped plug-in method names
  (`RESERVED_METHOD_NAMES`) are reserved, whatever the letter case.
- `jsampler check` takes a sampler file only and checks the method name before
  the options schema, `prepare` or drawing points. For a loaded method,
  `jsampler info <Method>` shows its source file.
- `jsampler list` and `info` show registered external methods.
- Human output, help and errors use rich panels and tables like `Jarvis`;
  `--json` prints one JSON object; `-v` prints a plain version line. Layout,
  errors and exit codes follow the
  [Jarvis CLI design](https://github.com/Pengxuan-Zhu-Phys/Jarvis-Books/blob/main/Docs/Ecosystem/JARVIS_CLI_DESIGN.md).

## 1.0.2 — 2026-10-15

- README install pin matches the package version.

## 1.0.1 — 2026-10-15

- `jsampler` command, with `-v` for the package version.
- Self-contained: `jsampler` manages only samplers in its own registry
  (`~/.jarvis/samplers`) and reads task cards with PyYAML. The package does not
  import Jarvis-HEP.

## 1.0.0 — 2026-10-15

- First release of the independent plug-in SDK. API version, stream protocol
  and registry format are 1.
