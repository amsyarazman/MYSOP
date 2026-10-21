from fastapi.testclient import TestClient
from app.main import app


def test_web_foundation_serves_local_assets(tmp_path, monkeypatch):
    monkeypatch.setenv('MYSOP_DB', str(tmp_path / 'web.sqlite3'))
    with TestClient(app) as client:
        page = client.get('/')
        assert page.status_code == 200
        assert 'Your kitchen playbook' in page.text
        assert '/static/app.js' in page.text
        assert client.get('/static/app.js').status_code == 200
        assert client.get('/static/style.css').status_code == 200
        assert client.get('/health').json() == {'status': 'ok'}
