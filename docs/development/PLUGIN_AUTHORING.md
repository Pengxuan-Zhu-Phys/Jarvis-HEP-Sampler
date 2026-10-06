# Plug-in authoring

A sampler plug-in is one `.py` file. Start from the template (`Jarvis sampler init <Name>`), edit it, load it (`Jarvis sampler load <file>`), then write `Sampling.Method: <Name>` in a task card.

The plug-in only produces points in the unit cube. Jarvis-HEP maps them through `Variables` and `Mapper`, applies `selection`, and runs them through Workers. You never touch Sample objects, UUIDs, Redis or the DATABASE.

## File contents

| Name | Required | Purpose |
| --- | --- | --- |
| `PLUGIN` | yes | Metadata dict, JSON data only (below) |
| `OPTIONS_SCHEMA` | no | JSON Schema (draft 2020-12) for your Bounds options. Leave it out, or set it to `None`, and your options are not checked |
| `prepare(setup)` | no | Runs once per scan, and again on resume. Returns the `plan` passed to `draw` |
| `draw(context, rng, plan)` | yes, unless you use blocks | Returns one point |
| `draw_block(context, rng, plan)` | with `block_size` | Returns `block_size` points at once |
| `validate_options(options)` | no | Raise to reject options, beyond what the schema checks |
| `settings_rows(setup, plan)` | no | Extra rows for the settings table |
| `summary_rows(plan, stats)` | no | Extra rows for the summary table |
| `stop_reason(plan, stats)` | no | Stop reason for the summary |
| `status(plan, stats)` | no | Metrics for the monitor |

You may import any library installed in your environment. Missing imports fail at `load`, at `check`, or when the run starts.

## `PLUGIN`

| Key | Required | Value |
| --- | --- | --- |
| `api_version` | yes | `1` |
| `method` | yes | The `Sampling.Method` name. It must look like a built-in name: an upper-case letter, then 1–63 letters or digits (`LatinHypercube`). It cannot be a built-in name, in any letter case |
| `version` | yes | Your version string. Change it whenever the algorithm changes meaning: a scan cannot resume across a version change |
| `profile` | yes | `"independent"`. `"generational"` is reserved for feedback samplers in a later release |
| `description` | no | One line, shown by `Jarvis man` and `Jarvis sampler list` |
| `statistical` | no | `True` turns on the same Mapper warnings as the statistical built-in methods. It does not make your points posterior samples |
| `block_size` | no | Use `draw_block` with blocks of this size instead of `draw` |

Unknown keys are an error, so a typo cannot pass silently.

## Bounds: reserved keys and your options

| Key | Owner | Rule |
| --- | --- | --- |
| `seed` | Jarvis-HEP | Non-negative integer, default `0` |
| `point_number` | Jarvis-HEP | Positive integer, required. The number of candidates; points rejected by `selection` count |
| `max_worker` | Jarvis-HEP | Run-time in-flight limit |
| everything else | you | Your options, available as `setup.options` / `context.options` |

Options must be JSON data (strings, numbers, booleans, null, lists, mappings). Inside the plug-in they are read-only: lists arrive as tuples and mappings cannot be changed. Schema `default` values are not filled in; use `options.get("key", default)`.

## Contexts

| Field | `setup` | `context` (draw) | `context` (draw_block) |
| --- | --- | --- | --- |
| `seed` | ✓ | | |
| `point_number`, `dimension`, `variable_names`, `options`, `log` | ✓ | ✓ | ✓ |
| `rng()` | ✓, a generator reserved for `prepare` | | |
| `candidate_index` | | ✓ | |
| `block_index`, `block_size` | | | ✓ |

`variable_names` follows the order of `Variables` in the task card, and `dimension` is its length.

## Points

- `draw` returns a 1-D array, list or tuple of length `dimension`.
- `draw_block` returns shape `(block_size, dimension)` for candidates `[block_index * block_size, (block_index + 1) * block_size)`. Rows past `point_number` are dropped.
- Values must be real numbers (not bool, complex or strings), finite, with `0 <= u <= 1`.
- After mapping, every physical value must also be finite. Jarvis-HEP checks this.

A bad point stops the scan with the candidate index and the component. Nothing is clipped or redrawn for you.

## Randomness and resume

Use the `rng` you are given; do not use `np.random.*` global functions, time or process IDs.

- `draw` gets a generator that depends only on `(seed, candidate_index)`.
- `draw_block` gets one that depends only on `(seed, block_index)`.
- `prepare` uses `setup.rng()`.

Points are therefore the same whatever the number of Workers, batch size or completion order. A resumed scan reproduces them exactly within the same Python/NumPy environment.

`prepare` runs again on resume, so the plan must follow from `setup` alone. Module-level state is allowed but outside this guarantee. `Jarvis sampler check` catches the common case of drawing from an unseeded global generator.

## Logging and monitor

Every context has `log`. Jarvis-HEP writes the start, settings, ready, checkpoint, failure, result and summary records itself. Use `log` for the rest:

| Call | Record |
| --- | --- |
| `log.step(title, rows)` | A table per stage or generation (INFO) |
| `log.adjust(name, old, new, why)` | A setting you changed, ignored or clamped (WARNING) |
| `log.saved(what, path)` | `<What> saved to <path>` for a file you wrote (WARNING) |
| `log.info(...)`, `log.warning(...)`, `log.debug(...)` | Anything else |

`stats` in the hooks has `candidates`, `accepted` and `point_number`. `status` may return up to 8 scalar metrics, with strings of up to 32 characters; extra or non-scalar entries are dropped. A hook that raises is logged and skipped; it never stops the scan. Without `stop_reason`, the reason is `point_number reached`.

## Errors

| Error | When |
| --- | --- |
| `PluginLoadError` | The file does not import, `PLUGIN` is invalid, a required function is missing, or the name is taken |
| `PluginConfigError` | Options break the schema, or `validate_options` / `prepare` raised |
| `PluginOutputError` | `draw` / `draw_block` raised or returned a bad point |
| `PluginResumeMismatch` | A resumed scan does not match the original run |
| `RegistryError` | `~/.jarvis/samplers` is unreadable or a snapshot is broken |

Your own exception is chained to these, so its traceback reaches the log. A failing plug-in stops the scan; Jarvis-HEP never falls back to another sampler.

## The registry

`Jarvis sampler load` copies the file to `~/.jarvis/samplers/user_sources/<Method>-<hash>.py` and records it in `~/.jarvis/samplers/sources.json`. `JARVIS_SAMPLERS_HOME` moves that directory.

- Runs use the copy, not your working file. Edit, then load again.
- `Jarvis sampler list` marks a working file changed since the last load.
- Loading the same method again replaces the entry and deletes the old copy.

The registry belongs to your user account on one machine. Load the plug-in on every machine that runs the card.
