# Contributing

Jarvis-HEP-Sampler is the plug-in SDK for user-defined Jarvis-HEP samplers. Keep changes within the plug-in format: metadata, loading, the user registry, random streams, output checks, the logging facade, the template and the offline test kit.

Jarvis-HEP remains responsible for the `Jarvis sampler` CLI, task-card validation, mapping and `selection`, Sample UUIDs, Redis, Workers, archiving, checkpoints and resume, the sampler log, telemetry and monitor.

## Workflow

1. Create a branch for the change.
2. Build and install the complete package:

   ```bash
   ./jhsrel
   python -m pip install dist/0.1.0/*.whl
   ```

3. Make the smallest practical change.
4. Add or update tests for behavior changes.
5. Rebuild, install and run the checks after changing source:

   ```bash
   release_dir="$(mktemp -d)"
   ./jhsrel --output "$release_dir"
   python -m pip install --force-reinstall "$release_dir/"*.whl
   ruff check .
   python -m pytest
   ```

## Coding Style

- Follow the existing small-module style.
- Never import Jarvis-HEP, Redis or Portal.
- Keep `jarvis_hep_sampler.registry` free of NumPy and jsonschema imports.
- Plug-in failures raise a `PluginError` subclass, with the plug-in's own exception chained.
- The independent profile has one implementation, `IndependentSession`. Do not add a second code path that produces points.
- API version 1 is frozen. A change to what a plug-in file must contain, or to the random streams (`STREAM_PROTOCOL`), needs a design decision in the Jarvis-HEP design record first.

## Testing Expectations

- Use `pytest` and `tmp_path`.
- Never touch the real `~/.jarvis/samplers`. The autouse fixture in `tests/conftest.py` sets `JARVIS_SAMPLERS_HOME`.
- Write plug-ins for tests as source text through the `write_plugin` fixture.
- Every output-contract or metadata rule needs both an accepted and a rejected case.

## Pull Request Checklist

- The change fits Jarvis-HEP-Sampler ownership.
- `docs/development/PLUGIN_AUTHORING.md` is updated when the plug-in contract changes.
- `__all__` and `_LAZY_ATTRS` stay in sync.
- `ruff check .`, `python -m pytest` and `python -m build` pass.
