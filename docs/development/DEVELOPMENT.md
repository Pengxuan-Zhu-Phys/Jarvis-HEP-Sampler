# Development

The [development ledger](DEVELOPMENT_LEDGER.md) tracks the current native-use goal:
after `Jarvis sampler load <file>`, users follow the same task-card and run workflow
as built-in samplers, with external samplers managed through `Jarvis sampler`.
It records implementation status, review findings, and the SDK/HEP acceptance gates.

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

## Layout

| Module | Responsibility |
| --- | --- |
| `metadata.py` | `PLUGIN` validation, method-name rule, profiles (`KNOWN_PROFILES` frozen in API v1, `SUPPORTED_PROFILES` runnable now) |
| `loader.py` | Import a plug-in from bytes (hash = executed code), check functions and arity, `LoadedPlugin` |
| `options.py` | Reserved Bounds keys, read-only JSON options, `OPTIONS_SCHEMA` checks |
| `streams.py` | `STREAM_PROTOCOL` and the per-prepare / candidate / block / generation PCG64 streams |
| `output.py` | The output contract for `draw` / `draw_block` |
| `contexts.py` | `SetupContext`, `DrawContext`, `BlockContext`, `SamplerStats` |
| `log.py` | `SamplerLog` facade, `LogBackend` protocol, offline stdlib backend |
| `session.py` | `IndependentSession`: the one implementation of the independent profile |
| `registry.py` | `~/.jarvis/samplers` (`sources.json`, snapshots, lock). No NumPy or jsonschema import |
| `template.py`, `templates/` | The fixed template behind `Jarvis sampler init` |
| `testing.py` | `check_plugin`, `assert_conforms`, `run_offline`, `reference_stream` |

## Rules

- Never import `jarvishep2`, `redis` or `jarvis_portal`. A test enforces it.
- `jarvis_hep_sampler.registry` must stay importable without NumPy or jsonschema. Jarvis-HEP reads the registry while validating cards. A test enforces it.
- Top-level names are lazy (`__init__.__getattr__`). Add new exports to both `_LAZY_ATTRS` and `__all__`; a test checks that the two match.
- The independent profile has one implementation, `IndependentSession`. The offline driver and the Jarvis-HEP adapter both call it, so `check` and a real scan cannot drift apart.
- A plug-in failure becomes a `PluginError` subclass, with the plug-in's exception as `__cause__`.
- Reporting hooks are protected through return-value consumption and normalization;
  a lazy iterator or conversion error is a hook failure. Control-flow exceptions
  such as `KeyboardInterrupt` and `SystemExit` still propagate.
- Protocol 1 raw PCG64 vectors are pinned in `tests/test_stream_protocol.py`; shared
  offline/native replay checks alone cannot detect a stream change on both sides.
- Registry reads that execute code hold a shared lock only while obtaining and
  verifying the entry and payload. User imports run outside that lock. The
  `sources.json` replacement is the management commit point; failed cleanup is
  deferred in private `.pending_cleanup.json` and cannot turn a committed load
  or remove into a reported failure. Only explicitly retired snapshots are retried.

## What Jarvis-HEP calls

| Jarvis-HEP feature | SDK entry point |
| --- | --- |
| `Jarvis sampler init` | `write_template(method, output, reserved_names=<built-in names>)` |
| `Jarvis sampler check` | `testing.check_plugin(path, variable_names=… or dimension=…, options=…)` |
| `Jarvis sampler load` | `SamplerRegistry().load(path, reserved_names=<built-in names>)` |
| `Jarvis sampler list` / `info` / `remove` | `SamplerRegistry().entries()`, `.source_state(entry)`, `.problems(entry)`, `.remove(method)` |
| Layered sampler catalog | `SamplerRegistry().entries()`, cached on `.signature()` |
| `Jarvis validate` | `split_bounds`, `parse_reserved`, `schema_issues(entry.options_schema, freeze_options(options))` |
| Run preflight | `load_plugin_source(<verified bytes>)` from the registry or scan binding, then `IndependentSession.from_bounds(...).prepare()` |
| `PluginSampler` adapter | `session.point(i)`, `session.settings_rows()` / `summary_rows()` / `stop_reason()` / `status()`, with `SamplerLog(method, <HEP backend>)` |
| Adapter tests | `reference_stream` for wiring; an analytic indexed sequence for independent correctness evidence |
| Scan identity | `STREAM_PROTOCOL`, `PLUGIN` metadata, `thaw_options(session.options)` |

The design record is `docs/jarvis-hep-sampler/technical-design.md` in the Jarvis-HEP repository.

## Native recovery acceptance

The [M2 verification record](M2_VERIFICATION.md) covers sparse durable rows, terminal failures, a rejection-only tail, registry updates/removal during active scans, and resource startup retry. The HEP host reconstructs prefix and pending accepted indices from DATABASE; `FixedSetSampler` skips durable rows at submission and returns the actual new task count. Candidate generation and the SDK protocol do not change. Failed durable rows remain terminal, and the pending set is not checkpointed.
