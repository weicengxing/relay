from pathlib import Path

_APP_PARTS = [
    "00_imports_config.py",
    "01_database.py",
    "02_shared_helpers.py",
    "03_schemas_app.py",
    "04_auth_billing_keys.py",
    "05_admin.py",
    "06_models_announcements_redeem.py",
    "07_novels.py",
    "08_web_chat_routes_history.py",
    "09_web_chat_sessions_streaming.py",
    "10_web_chat_images_sources.py",
    "11_web_chat_client.py",
    "12_web_chat_handoff_events.py",
    "13_openai_compat.py",
    "14_proxy_billing_settings.py",
]
_APP_PARTS_DIR = Path(__file__).with_name("app_parts")

for _part_name in _APP_PARTS:
    _part_path = _APP_PARTS_DIR / _part_name
    exec(compile(_part_path.read_text(encoding="utf-8"), str(_part_path), "exec"), globals())

del _APP_PARTS, _APP_PARTS_DIR, _part_name, _part_path

__all__ = ["app"]
