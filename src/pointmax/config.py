"""Paths and user config (~/.config/pointmax/config.toml).

M0 defines the paths only; the CPP table, home airports, buffers and ring settings
arrive with `pointmax config` in M3.
"""

import os
from pathlib import Path


def config_dir() -> Path:
    """`$POINTMAX_HOME`, else `$XDG_CONFIG_HOME/pointmax`, else `~/.config/pointmax`."""
    if home := os.environ.get("POINTMAX_HOME"):
        return Path(home)
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "pointmax"


def session_path() -> Path:
    return config_dir() / "session.json"


def chrome_profile_dir() -> Path:
    return config_dir() / "chrome-profile"


def config_path() -> Path:
    return config_dir() / "config.toml"


DEFAULT_HOME_AIRPORTS = ("AUS", "DFW")
