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

`jsampler` is this package's command. It only sees samplers loaded into `~/.jarvis/samplers`. `Jarvis sampler` is Jarvis-HEP's command and also knows the built-in methods. `jsampler -v` prints this package's version. `jsampler --json` prints one plain JSON object. The SDK also supports offline Python use (see [Python API](#python-api)).

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

Version 1.0.2. Install from PyPI:

```bash
python -m pip install "Jarvis-HEP-Sampler==1.0.2"
```

From this repository:

```bash
python -m pip install .
```

Dependencies: NumPy, jsonschema, PyYAML and rich. A sampler-enabled Jarvis-HEP installs this SDK with `Jarvis-HEP-Sampler>=1.0.0,<2`.

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

The full contract is in [Plug-in authoring](docs/development/PLUGIN_AUTHORING.md).

A complete runnable card is provided in
[examples/MyLatinHypercube.task.yaml](examples/MyLatinHypercube.task.yaml).
It uses Jarvis-HEP's bundled Eggbox demonstration operator:

```bash
jsampler check examples/MyLatinHypercube.py --card examples/MyLatinHypercube.task.yaml
jsampler load examples/MyLatinHypercube.py
Jarvis validate examples/MyLatinHypercube.task.yaml
Jarvis check examples/MyLatinHypercube.task.yaml
Jarvis run examples/MyLatinHypercube.task.yaml
```

`jsampler check` checks a sampler file, or a sampler already loaded by this package. A file does not need `load` first. `Jarvis check` is the calculator smoke: its identity, bound source and checkpoint stay under `DATABASE/test` and `checkpoints/<scan>/<Method>/check/`, and the formal scan's science database and resume checkpoint stay in place.

Reloading the same method updates future scans. Removing the registration
preserves an existing scan's bound source and its normal `Jarvis run ... --resume`
workflow.

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

- [Plug-in authoring](docs/development/PLUGIN_AUTHORING.md)

## Status

Alpha. API version 1 supports the independent execution contract; generational metadata reserves a future profile, whose running state/feedback contract remains under design. This release runs `independent` plug-ins; `generational` (feedback samplers) arrives in a later release.

## License

MIT. See [LICENSE](LICENSE). Copyright (c) 2026 Pengxuan Zhu.
