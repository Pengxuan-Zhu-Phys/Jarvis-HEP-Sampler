# Jarvis-HEP-Sampler

Jarvis-HEP-Sampler is the plug-in SDK for user-defined samplers in the Jarvis ecosystem.

A user writes a sampler as one Python file, loads it once, and from then on uses it in a task card exactly like a built-in method. No Jarvis-HEP source code is changed. The plug-in's points go through the same Redis queue, logging, monitor, checkpoint and resume machinery as `Random` or `Bridson`.

```text
Jarvis sampler init LatinHypercube       # fixed template -> ./LatinHypercube.py
#   edit draw() (and optionally OPTIONS_SCHEMA)
Jarvis sampler check LatinHypercube.py   # optional offline check, no Redis
Jarvis sampler load LatinHypercube.py    # snapshot into ~/.jarvis/samplers; reloading replaces it
Jarvis run task.yaml                     # Sampling.Method: LatinHypercube
```

The `Jarvis sampler` commands are part of Jarvis-HEP and use this package. Until they ship, the same steps are available from Python (see [Python API](#python-api)).

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

Jarvis-HEP owns the runtime:

- the `Jarvis sampler` CLI
- task-card validation
- the run preflight
- mapping unit-cube points to physical parameters, and `selection`
- Sample UUIDs, Redis, Workers and the Archiver
- checkpoints and resume
- the sampler log, telemetry and monitor
- `Jarvis man` and project packing

This package never imports Jarvis-HEP, Redis or Portal.

## Quick Install

```bash
pip install Jarvis-HEP-Sampler
```

Dependencies: NumPy and jsonschema. Jarvis-HEP installs this package for you.

## A plug-in

```python
"""Latin hypercube design: one point per stratum in every variable."""

import numpy as np

PLUGIN = {
    "api_version": 1,
    "method": "LatinHypercube",
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
  Method: LatinHypercube
  Variables:
    - name: mass
      distribution: {type: Flat, parameters: {min: 100.0, max: 1000.0}}
  Bounds:
    seed: 7
    point_number: 10000
    centered: false
```

The full contract is in [Plug-in authoring](docs/development/PLUGIN_AUTHORING.md).

## Python API

```python
from jarvis_hep_sampler import SamplerRegistry, write_template
from jarvis_hep_sampler.testing import check_plugin, run_offline

path = write_template("LatinHypercube")                  # Jarvis sampler init
report = check_plugin(path, dimension=2, options={})     # Jarvis sampler check
for name, result in report.rows():
    print(f"{name:14} {result}")

run = run_offline(path, variable_names=["mass", "coupling"], point_number=1000, seed=7)
print(run.points.shape, run.stop_reason)

SamplerRegistry().load(path)                             # Jarvis sampler load
```

## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest
ruff check .
python -m build
```

## Documentation

- [Docs index](docs/README.md)
- [Plug-in authoring](docs/development/PLUGIN_AUTHORING.md)
- [Development](docs/development/DEVELOPMENT.md)
- [Release](docs/release/RELEASE.md)
- [Contributing](CONTRIBUTING.md)
- Design record: `docs/jarvis-hep-sampler/technical-design.md` in the Jarvis-HEP repository

## Status

Alpha. API version 1 is frozen for the `independent` and `generational` profiles. This release runs `independent` plug-ins; `generational` (feedback samplers) arrives in a later release.
