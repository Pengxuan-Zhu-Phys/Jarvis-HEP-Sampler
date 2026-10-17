# Jarvis-HEP-Sampler

Jarvis-HEP-Sampler is the plug-in SDK for user-defined samplers in the Jarvis ecosystem.

A user writes a sampler as one Python file, loads it once, and from then on uses it in a task card exactly like a built-in method. No Jarvis-HEP source code is changed. The plug-in's points go through the same Redis queue, logging and monitor as built-in samplers. The sampler-enabled HEP branch binds each scan to an exact source snapshot and checks scientific settings before resume. Project packages include the source and its full hash; fetch verifies it and prints a load command.

```text
jsampler init MyLatinHypercube       # fixed template -> ./MyLatinHypercube.py
#   edit draw() (and optionally OPTIONS_SCHEMA)
jsampler check MyLatinHypercube.py   # optional offline check, no Redis
jsampler load MyLatinHypercube.py    # snapshot into ~/.jarvis/samplers; reloading replaces it
Jarvis run task.yaml                 # Sampling.Method: MyLatinHypercube
```

`jsampler` is this package's command for creating and checking sampler files and managing registrations in `~/.jarvis/samplers`. Its `list` and `info` commands show registered external methods. `Jarvis sampler` is Jarvis-HEP's command and also knows the built-in methods. `jsampler -v` prints this package's version. `jsampler --json` prints one plain JSON object. The SDK also supports offline Python use (see [Python API](#python-api)).

## Scope

Jarvis-HEP-Sampler owns the plug-in format:

- the fixed template
- the `PLUGIN` metadata rules and method-name rule
- loading a plug-in file
- the user registry in `~/.jarvis/samplers/`
- the deterministic random streams
- the output contract (shape, real, finite, inside `[0, 1]`)
- the `log` facade handed to plug-ins
- the offline driver and conformance checks
- the `jsampler` command

Jarvis-HEP owns the runtime:

- `Jarvis sampler`, for built-in methods and loaded plug-ins
- task-card validation
- the run preflight
- mapping unit-cube points to physical parameters, and `selection`
- Sample UUIDs, Redis, Workers and the Archiver
- checkpoints and resume
- the sampler log, telemetry and monitor
- `Jarvis man` and project packing

This package does not import Jarvis-HEP, Redis or Portal. `jsampler check --card` reads `Sampling.Variables` and `Sampling.Bounds` from the task YAML.

## Complete package installation

Published package: Version 1.1.1. Install from PyPI:

```bash
python -m pip install "Jarvis-HEP-Sampler==1.1.1"
```

From this repository:

```bash
python -m pip install .
```

Dependencies: NumPy, jsonschema, PyYAML and rich. Jarvis-HEP 2.1.0 and later require host contract 2, provided by Jarvis-HEP-Sampler 1.1.0 and later.

The end-to-end user tutorial lives in Jarvis-Books, in the TeX manual chapter **Jarvis-HEP-Sampler: Implementing Your Own Sampler** (`TeX/Jarvis-HEP-V2 manual`).

## A plug-in

```python
"""Latin hypercube design: one point per stratum in every variable."""

import numpy as np

PLUGIN = {
    "api_version": 1,
    "method": "MyLatinHypercube",
    "version": "0.1.0",
    "profile": "independent",
}

OPTIONS_SCHEMA = {  # optional
    "type": "object",
    "properties": {"centered": {"type": "boolean"}},
    "additionalProperties": False,
}


def prepare(setup):
    rng = setup.rng()
    perms = np.stack([rng.permutation(setup.point_number) for _ in range(setup.dimension)])
    return {"perms": perms, "centered": bool(setup.options.get("centered", False))}


def draw(context, rng, plan):
    strata = plan["perms"][:, context.candidate_index]
    offset = 0.5 if plan["centered"] else rng.random(context.dimension)
    return (strata + offset) / context.point_number
```

```yaml
Sampling:
  Method: MyLatinHypercube
  Variables:
    - name: mass
      distribution: {type: Flat, parameters: {min: 100.0, max: 1000.0}}
  Bounds:
    seed: 7
    point_number: 10000
    centered: false
```

The full contract is in [Plug-in authoring](https://github.com/Pengxuan-Zhu-Phys/Jarvis-Books/blob/main/Docs/Jarvis-HEP-Sampler/PLUGIN_AUTHORING.md).

A complete runnable card is provided in
[examples/MyLatinHypercube.task.yaml](https://github.com/Pengxuan-Zhu-Phys/Jarvis-HEP-Sampler/blob/main/examples/MyLatinHypercube.task.yaml).
It uses Jarvis-HEP's bundled Eggbox demonstration operator:

```bash
jsampler check examples/MyLatinHypercube.py --card examples/MyLatinHypercube.task.yaml
jsampler load examples/MyLatinHypercube.py
Jarvis validate examples/MyLatinHypercube.task.yaml
Jarvis check examples/MyLatinHypercube.task.yaml
Jarvis run examples/MyLatinHypercube.task.yaml
```

`jsampler check` accepts a sampler file only and does not need `load` first. It checks the method name before options schema, `prepare` or drawing points. A reserved-name failure returns exit 2; algorithm output or repeatability failures return exit 1. For a loaded method, use `jsampler info <Method>` to find its source file, then check that file. `Jarvis check` is the calculator smoke: its identity, bound source and checkpoint stay under `DATABASE/test` and `checkpoints/<scan>/<Method>/check/`, and the formal scan's science database and resume checkpoint stay in place.

The command-line layout, errors, exit codes and JSON format follow the [Jarvis CLI design](https://github.com/Pengxuan-Zhu-Phys/Jarvis-Books/blob/main/Docs/Ecosystem/JARVIS_CLI_DESIGN.md).

Reloading the same method updates future scans. Removing the registration
preserves an existing scan's bound source and its normal `Jarvis run ... --resume`
workflow.

## Host integration

`HOST_CONTRACT_VERSION = 2` identifies the host-facing interface since 1.1.0;
plug-in `API_VERSION` and the stream protocol remain 1. `check_method_name` and
`parse_metadata` validate syntax and structure. External `init`, registry `load`
and `check_plugin` apply `check_external_method_name`; generic loaders accept
packaged names without a trusted-name override. Entry policies run through the
optional `metadata_validator` loader hook before options schemas and hooks.

`jarvis_hep_sampler.cli.main(..., catalog=CatalogExtension(...))` accepts host
data callbacks `augment_list(payload)` and `resolve_info(method, payload)`, plus
`list_sections=((payload_key, panel_title), ...)`. They add fields to the SDK
results; parsing, errors and both text/JSON rendering stay in the SDK. Host
`info` can include `conflicts` with exact method names, problems and removal
commands. Existing JSON fields remain intact.

## Python API

```python
from jarvis_hep_sampler import SamplerRegistry, write_template
from jarvis_hep_sampler.testing import check_plugin, run_offline

path = write_template("MyLatinHypercube")                  # jsampler init
report = check_plugin(path, dimension=2, options={})     # jsampler check
for name, result in report.rows():
    print(f"{name:14} {result}")

run = run_offline(path, variable_names=["mass", "coupling"], point_number=1000, seed=7)
print(run.points.shape, run.stop_reason)

SamplerRegistry().load(path)                             # jsampler load
```

## Documentation

- [Plug-in authoring](https://github.com/Pengxuan-Zhu-Phys/Jarvis-Books/blob/main/Docs/Jarvis-HEP-Sampler/PLUGIN_AUTHORING.md)
- [Developer documentation](https://github.com/Pengxuan-Zhu-Phys/Jarvis-Books/blob/main/Docs/Jarvis-HEP-Sampler/README.md)
- [Changelog](https://github.com/Pengxuan-Zhu-Phys/Jarvis-HEP-Sampler/blob/main/CHANGELOG.md)

## Status

Alpha. API version 1 supports the independent execution contract; generational metadata reserves a future profile, whose running state/feedback contract remains under design. This release runs `independent` plug-ins; `generational` (feedback samplers) arrives in a later release.

## License

MIT. See [LICENSE](https://github.com/Pengxuan-Zhu-Phys/Jarvis-HEP-Sampler/blob/main/LICENSE). Copyright (c) 2026 Pengxuan Zhu.
