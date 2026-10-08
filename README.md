# Jarvis-HEP-Sampler

Jarvis-HEP-Sampler is the plug-in SDK for user-defined samplers in the Jarvis ecosystem.

A user writes a sampler as one Python file, loads it once, and from then on uses it in a task card exactly like a built-in method. No Jarvis-HEP source code is changed. The plug-in's points go through the same Redis queue, logging and monitor as built-in samplers. The sampler-enabled HEP branch binds each scan to an exact source snapshot and checks scientific settings before resume. Project packages include the source and its full hash; fetch verifies it and prints a load command.

```text
Jarvis sampler init MyLatinHypercube       # fixed template -> ./MyLatinHypercube.py
#   edit draw() (and optionally OPTIONS_SCHEMA)
Jarvis sampler check MyLatinHypercube.py   # optional offline check, no Redis
Jarvis sampler load MyLatinHypercube.py    # snapshot into ~/.jarvis/samplers; reloading replaces it
Jarvis run task.yaml                     # Sampling.Method: MyLatinHypercube
```

The `Jarvis sampler` commands are part of Jarvis-HEP and use this package. They are available in the sampler-enabled Jarvis-HEP development branch. The SDK also supports offline Python use (see [Python API](#python-api)).

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

## Complete package installation

The first PyPI release is pending. Install your local checkout before installing the sampler-enabled Jarvis-HEP branch:

```bash
cd Jarvis-HEP-Sampler
./jhsrel
python -m pip install dist/0.1.0/*.whl
```

Dependencies: NumPy and jsonschema. Published Jarvis-HEP versions that support samplers will install the SDK as a dependency.

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

## Python API

```python
from jarvis_hep_sampler import SamplerRegistry, write_template
from jarvis_hep_sampler.testing import check_plugin, run_offline

path = write_template("MyLatinHypercube")                  # Jarvis sampler init
report = check_plugin(path, dimension=2, options={})     # Jarvis sampler check
for name, result in report.rows():
    print(f"{name:14} {result}")

run = run_offline(path, variable_names=["mass", "coupling"], point_number=1000, seed=7)
print(run.points.shape, run.stop_reason)

SamplerRegistry().load(path)                             # Jarvis sampler load
```

## Development

After source changes, rebuild and verify the complete package before testing an installation:

```bash
python -m pip install pytest ruff
release_dir="$(mktemp -d)"
./jhsrel --output "$release_dir"
python -m pip install --force-reinstall "$release_dir/"*.whl
python -m pytest
ruff check .
```

The helper runs all SDK tests against the installed wheel in a separate fresh venv. Reinstalling the complete wheel makes local tests use the new implementation as well. Tests isolate `JARVIS_SAMPLERS_HOME` and never touch the user's registration.

## Documentation

- [Docs index](docs/README.md)
- [Plug-in authoring](docs/development/PLUGIN_AUTHORING.md)
- [Development](docs/development/DEVELOPMENT.md)
- [Release](docs/release/RELEASE.md)
- [Contributing](CONTRIBUTING.md)
- Design record: `docs/jarvis-hep-sampler/technical-design.md` in the Jarvis-HEP repository

## Status

Alpha. API version 1 supports the independent execution contract; generational metadata reserves a future profile, whose running state/feedback contract remains under design. This release runs `independent` plug-ins; `generational` (feedback samplers) arrives in a later release.

## Complete package release

Run `./jhsrel` (or source it and call `jhsrel`) to build one complete wheel and
source distribution, install all declared dependencies in a fresh virtual environment,
run the installed SDK smoke and full SDK tests, and write checksums plus
`release-verification.json` under `dist/<version>/`. There are no dependency extras
or editable installation paths. Build/test tools do not change the shipped library.

`./jhsrel X.Y.Z --upload` updates the two version files and uploads only after
verification. Omit `--upload` to prepare locally. Pass `--output DIR` to select an
empty artifact directory. No upload is performed during implementation.
