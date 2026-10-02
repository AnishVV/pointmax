from pointmax import config


def test_pointmax_home_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("POINTMAX_HOME", str(tmp_path))
    assert config.session_path() == tmp_path / "session.json"
    assert config.chrome_profile_dir() == tmp_path / "chrome-profile"


def test_xdg_default(monkeypatch, tmp_path):
    monkeypatch.delenv("POINTMAX_HOME", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert config.config_path() == tmp_path / "pointmax" / "config.toml"
