# Release

Do not publish from a development session unless the task is the release itself. Normal development stops after a local build check.

## Versions

The package version lives in two places, which a test keeps equal:

- `pyproject.toml`
- `src/jarvis_hep_sampler/_version.py`

These are separate from the package version:

- **API version** (`API_VERSION`): what a plug-in file must contain. It is 1 and frozen.
- **Stream protocol** (`STREAM_PROTOCOL`): how random streams are derived. It is 1. Changing it changes every point of every plug-in, so it needs a design decision first.
- **Registry version**: the format of `sources.json`. It is 1.

Jarvis-HEP depends on `Jarvis-HEP-Sampler>=0.1`. Raise that floor in Jarvis-HEP when it starts using a new SDK feature.

## Build Checklist

```bash
python -m pip install -e ".[dev]"
ruff check .
python -m pytest
python -m build
twine check dist/*
```

## Local release helper

```bash
source ./jhsrel
jhsrel 0.1.1
jhsrel 0.1.1 -v
```

`jhsrel` does the following, then uploads with `twine upload -r pypi`:

1. updates both version files;
2. cleans build artifacts;
3. builds and checks the distributions;
4. reinstalls the package in editable mode;
5. verifies the installed and runtime versions;
6. checks a generated template and loads it into a temporary registry.

## GitHub Release Process

1. Confirm CI passes on the release commit.
2. Tag the commit `vX.Y.Z` and push the tag.
3. Draft a GitHub release with short notes: changed behavior, compatibility, known limits.
4. Publish the release. `.github/workflows/publish.yml` checks that the tag, `pyproject.toml` and `_version.py` agree, runs the tests, builds, and publishes through PyPI Trusted Publishing (`environment: pypi`).

Trusted Publishing must be set up once on PyPI for the `Jarvis-HEP-Sampler` project, and a `pypi` environment must exist in the GitHub repository.
