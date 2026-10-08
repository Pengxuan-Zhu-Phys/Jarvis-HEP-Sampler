"""Private subprocess worker used by testing.check_plugin; no public CLI."""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import numpy as np

from jarvis_hep_sampler.loader import load_plugin_source
from jarvis_hep_sampler.session import IndependentSession


def main() -> None:
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    plugin = load_plugin_source(base64.b64decode(data["source"]), origin=data["origin"])
    session = IndependentSession(
        plugin, seed=data["seed"], point_number=data["point_number"],
        variable_names=data["variable_names"], options=data["options"],
    )
    session.prepare()
    tail = np.array([u for _, u in session.points(data["start"])])
    np.save(sys.argv[2], tail, allow_pickle=False)


if __name__ == "__main__":
    main()
