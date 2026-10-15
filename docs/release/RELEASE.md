# Release

The same complete wheel and source distribution are used for development, CI and users. Dependency extras and editable installations are not supported. Test/build tools are installed separately and do not create a second package variant.

## Version and compatibility

The distribution version appears in `pyproject.toml` and `src/jarvis_hep_sampler/_version.py`. The helper updates both when given an explicit X.Y.Z argument. The first public distribution version is 1.0.0. API version 1, stream protocol 1 and registry format 1 are separate contracts and stay at 1. The sampler-enabled Jarvis-HEP requires `Jarvis-HEP-Sampler>=1.0.0,<2`.

Publish the SDK before a HEP release that depends on it. This repository has not been uploaded during the implementation work.

## Prepare complete artifacts

```bash
./jhsrel
# Or choose a new version and a fresh destination:
./jhsrel 0.1.1 --output dist/0.1.1
python -m pip install dist/0.1.1/*.whl
```

The helper can also be sourced in Bash or Zsh, then called as `jhsrel`. Without `--upload` it only prepares locally. `--dry` is a compatibility alias for this default and cannot be combined with `--upload`.

It snapshots tracked files from the current checkout, including current edits. Add intended new files to Git before preparing a release; unrelated untracked files are excluded. It builds the sdist and a wheel from that sdist in an isolated build environment, checks both with Twine, installs the complete wheel and every declared dependency in a new venv, runs `pip check`, and verifies imports originate inside that venv. It exercises template generation, the checker in another process and the registry, then runs all SDK tests against the installed wheel from outside the checkout. No sibling source tree or PYTHONPATH is used.

Artifacts are copied to `dist/<version>/` only after verification succeeds, together with `SHA256SUMS` and `release-verification.json`. The latter records artifact hashes and installed dependency versions. Existing distributions are never overwritten: use a new empty `--output` directory for another attempt. `--python /path/to/python` selects the test interpreter. Check `ruff check .` before releasing; Linux/macOS and Python 3.10–3.13 CI install the same complete wheel. CI configuration is not evidence that the remote matrix has run.

## Publish explicitly

```bash
./jhsrel 0.1.1 --output dist/0.1.1-publish --upload
```

Only this explicit flag uploads, after all local checks pass. Set the usual Twine token environment variables or keyring credentials; no credentials belong in Git. The helper uses noninteractive Twine upload and propagates errors. A version already present on PyPI requires a new version, not replacement of published files.

Alternatively, publish a GitHub release tagged `vX.Y.Z`. The publish workflow checks the tag and both version files, runs this same complete-package helper, and publishes only the wheel/sdist through PyPI Trusted Publishing. Configure the `pypi` environment and trusted publisher on PyPI beforehand. Local preparation does not create tags, push commits, or publish a GitHub release.
