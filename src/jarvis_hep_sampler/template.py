"""The fixed plug-in template behind ``jsampler init`` (technical design §5.5)."""

from __future__ import annotations

from collections.abc import Iterable
from importlib import resources
from pathlib import Path

from jarvis_hep_sampler.errors import PluginLoadError
from jarvis_hep_sampler.metadata import INDEPENDENT, SUPPORTED_PROFILES, check_external_method_name

PLACEHOLDER = "__METHOD__"


def render_template(
    method: str, *, profile: str = INDEPENDENT, reserved_names: Iterable[str] = ()
) -> str:
    """Return the template text for *method*."""
    check_external_method_name(method, reserved_names=reserved_names)
    if profile not in SUPPORTED_PROFILES:
        raise PluginLoadError(
            f"no template for profile {profile!r}; available: {', '.join(SUPPORTED_PROFILES)}"
        )
    template = (
        resources.files("jarvis_hep_sampler")
        .joinpath("templates")
        .joinpath(f"{profile}.py.tmpl")
        .read_text(encoding="utf-8")
    )
    return template.replace(PLACEHOLDER, method)


def write_template(
    method: str,
    output: str | Path | None = None,
    *,
    profile: str = INDEPENDENT,
    reserved_names: Iterable[str] = (),
) -> Path:
    """Write ``<method>.py`` (or *output*) from the template; never overwrite a file.

    *output* may be a file path or an existing directory.
    """
    text = render_template(method, profile=profile, reserved_names=reserved_names)
    if output is None:
        target = Path.cwd() / f"{method}.py"
    else:
        target = Path(output).expanduser()
        if target.is_dir():
            target = target / f"{method}.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(target, "x", encoding="utf-8") as handle:
            handle.write(text)
    except FileExistsError as exc:
        raise FileExistsError(
            f"{target} already exists; choose another --output or remove the file"
        ) from exc
    return target


__all__ = ["PLACEHOLDER", "render_template", "write_template"]
