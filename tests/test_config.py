from pointmax import config


def test_pointmax_home_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("POINTMAX_HOME", str(tmp_path))
    assert config.session_path() == tmp_path / "session.json"
    assert config.chrome_profile_dir() == tmp_path / "chrome-profile"


def test_xdg_default(monkeypatch, tmp_path):
    monkeypatch.delenv("POINTMAX_HOME", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert config.config_path() == tmp_path / "pointmax" / "config.toml"


def test_defaults_load(tmp_path):
    s = config.load_settings(tmp_path / "missing.toml")
    assert s.home == ["AUS", "DFW"]
    assert s.cpp_for("chase ultimate rewards") == 2.05
    assert s.cpp_for("Unknown Program") == 1.2
    assert s.ring_caps == {1: 5, 2: 6, 3: 6}


def test_user_file_overrides_partially(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('home = ["sat"]\n[cpp]\n"Bilt" = 2.5\n[balances]\n"Air Canada Aeroplan" = 80000\n')
    s = config.load_settings(p)
    assert s.home == ["SAT"]
    assert s.cpp_for("Bilt") == 2.5 and s.cpp_for("Air Canada Aeroplan") == 1.5  # others kept
    assert s.balances == {"Air Canada Aeroplan": 80000}


def test_cash_estimate_bands(tmp_path):
    s = config.load_settings(tmp_path / "x.toml")
    assert s.cash_estimate(100) == 90
    assert s.cash_estimate(300) == 130
    assert s.cash_estimate(99999) == 380


def test_write_default_does_not_clobber(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("home = []\n")
    config.write_default(p)
    assert p.read_text() == "home = []\n"
