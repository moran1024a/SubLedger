from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

with patch("app.security.load_or_create_fernet_key", return_value=object()):
    from app.main import create_app


def make_settings(tmp_path: Path):
    return SimpleNamespace(
        app=SimpleNamespace(timezone="UTC"),
        database=SimpleNamespace(
            host="127.0.0.1",
            port=3306,
            username="test",
            password="test",
            database="subledger_test",
            charset="utf8mb4",
            pool_size=1,
            max_overflow=0,
            pool_recycle=1800,
            pool_timeout=1,
            connect_timeout=1,
        ),
        scheduler=SimpleNamespace(enabled=False),
        logging=SimpleNamespace(directory=str(tmp_path / "logs")),
        security=SimpleNamespace(secret_key_file=str(tmp_path / "fernet.key")),
    )


def test_spa_assets_fallback_and_reserved_routes(tmp_path: Path, monkeypatch):
    static_dir = tmp_path / "static"
    assets_dir = static_dir / "assets"
    assets_dir.mkdir(parents=True)
    (static_dir / "index.html").write_text("<main>SubLedger</main>", encoding="utf-8")
    (assets_dir / "app-a1b2c3.js").write_text("console.log('ok')", encoding="utf-8")
    monkeypatch.setenv("SUBLEDGER_STATIC_DIR", str(static_dir))

    client = TestClient(create_app(make_settings(tmp_path)))

    asset = client.get("/assets/app-a1b2c3.js")
    assert asset.status_code == 200
    assert asset.text == "console.log('ok')"
    assert asset.headers["cache-control"] == "public, max-age=31536000, immutable"

    missing_asset = client.get("/assets/missing.js", headers={"Accept": "text/html"})
    assert missing_asset.status_code == 404
    assert "SubLedger" not in missing_asset.text
    assert client.get("/assets", headers={"Accept": "text/html"}).status_code == 404

    navigation = client.get("/plans", headers={"Accept": "text/html"})
    assert navigation.status_code == 200
    assert navigation.text == "<main>SubLedger</main>"
    assert navigation.headers["cache-control"] == "no-cache"

    admin_navigation = client.get("/admin/users", headers={"Accept": "text/html"})
    assert admin_navigation.status_code == 200
    assert admin_navigation.text == "<main>SubLedger</main>"
    assert admin_navigation.headers["cache-control"] == "no-cache"

    head_navigation = client.head("/plans", headers={"Accept": "text/html"})
    assert head_navigation.status_code == 200
    assert head_navigation.content == b""
    assert head_navigation.headers["cache-control"] == "no-cache"

    non_html = client.get("/plans", headers={"Accept": "application/json"})
    assert non_html.status_code == 404
    assert client.get("/missing.txt", headers={"Accept": "text/html"}).status_code == 404

    missing_api = client.get("/api/v1/missing", headers={"Accept": "text/html"})
    assert missing_api.status_code == 404
    assert "SubLedger" not in missing_api.text
    assert client.get("/health/missing", headers={"Accept": "text/html"}).status_code == 404
    assert client.get("/openapi.json/missing", headers={"Accept": "text/html"}).status_code == 404
