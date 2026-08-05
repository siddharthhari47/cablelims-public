"""
Regression tests for H14: centralized configuration via pydantic-settings
(app/config.py). Covers: defaults match the documented values, an env var
override actually takes effect, and the CORS field's comma-separated
parsing (added because pydantic-settings' default List[str] env parsing
expects JSON, which isn't friendly for a non-technical operator editing
.env by hand -- see app/config.py's NoDecode comment).
"""
from app.config import Settings


def test_defaults_match_documented_values():
    s = Settings(_env_file=None)
    assert s.access_token_expire_hours == 12
    assert s.login_max_failures == 5
    assert s.login_lockout_seconds == 15 * 60
    assert s.login_failure_window_seconds == 15 * 60
    assert s.max_upload_bytes == 10 * 1024 * 1024
    assert s.upload_jpeg_quality == 85
    assert s.log_max_bytes == 5 * 1024 * 1024
    assert s.log_backup_count == 5
    assert s.backup_default_keep == 30
    assert s.low_disk_space_bytes == 500 * 1024 * 1024
    assert s.db_busy_timeout_ms == 5000
    # H19: no longer a wildcard -- see config.py's own comment on this field.
    assert s.cors_allowed_origins == ["http://localhost:5173", "http://127.0.0.1:5173"]


def test_env_var_overrides_scalar_field(monkeypatch):
    monkeypatch.setenv("CABLELIMS_ACCESS_TOKEN_EXPIRE_HOURS", "1")
    s = Settings(_env_file=None)
    assert s.access_token_expire_hours == 1


def test_env_var_override_is_scoped_to_its_own_field(monkeypatch):
    # An override of one field must not disturb any other field's default --
    # each Settings field is independent.
    monkeypatch.setenv("CABLELIMS_LOGIN_MAX_FAILURES", "1")
    s = Settings(_env_file=None)
    assert s.login_max_failures == 1
    assert s.access_token_expire_hours == 12


def test_cors_origins_accepts_comma_separated_string(monkeypatch):
    monkeypatch.setenv("CABLELIMS_CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://192.168.1.50:5173")
    s = Settings(_env_file=None)
    assert s.cors_allowed_origins == ["http://localhost:5173", "http://192.168.1.50:5173"]


def test_cors_origins_strips_whitespace_and_drops_empty_entries(monkeypatch):
    monkeypatch.setenv("CABLELIMS_CORS_ALLOWED_ORIGINS", " http://a.local , , http://b.local ")
    s = Settings(_env_file=None)
    assert s.cors_allowed_origins == ["http://a.local", "http://b.local"]


def test_cors_origins_single_value_is_a_one_element_list(monkeypatch):
    monkeypatch.setenv("CABLELIMS_CORS_ALLOWED_ORIGINS", "http://localhost:5173")
    s = Settings(_env_file=None)
    assert s.cors_allowed_origins == ["http://localhost:5173"]


def test_unknown_env_vars_with_the_app_prefix_are_ignored(monkeypatch):
    # extra="ignore" in model_config -- a typo'd or since-removed setting
    # name must not crash the app at startup.
    monkeypatch.setenv("CABLELIMS_THIS_SETTING_DOES_NOT_EXIST", "whatever")
    Settings(_env_file=None)  # must not raise
