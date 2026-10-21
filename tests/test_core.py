import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('MYSOP_DB', str(tmp_path / 'test.sqlite3'))
    with TestClient(app) as client:
        yield client


def account(client, email):
    body = {'email': email, 'password': 'correct-horse-battery'}
    assert client.post('/auth/register', json=body).status_code == 201
    response = client.post('/auth/login', json=body)
    assert response.status_code == 200
    return {'Authorization': 'Bearer ' + response.json()['access_token']}


def recipe(title='Iced latte', category='drink'):
    return {'title': title, 'category': category, 'ingredients': [{'name': 'Milk', 'quantity': 200, 'unit': 'ml'}], 'steps': ['Measure milk', 'Add espresso and ice'], 'allergens': ['Milk'], 'safety_notes': 'Keep milk refrigerated.'}


def setup_team(client):
    owner = account(client, 'owner@example.com')
    member = account(client, 'member@example.com')
    team = client.post('/teams', headers=owner, json={'name': 'Cafe'}).json()['id']
    token = client.post(f'/teams/{team}/invitations', headers=owner).json()['invitation_token']
    assert client.post('/teams/join', headers=member, json={'invitation_token': token}).status_code == 200
    return owner, member, team


def test_publish_live_update_and_immutable_history(client):
    owner, member, team = setup_team(client)
    root = f'/teams/{team}'
    draft = client.post(root + '/sops', headers=owner, json=recipe()).json()
    sop = draft['id']
    assert client.get(root + '/sops', headers=member).json() == []
    assert client.get(root + '/drafts', headers=member).json() == []
    with client.websocket_connect(root + '/live') as ws:
        ws.send_json({'token': member['Authorization'].split()[1]})
        assert ws.receive_json()['type'] == 'ready'
        published = client.post(root + f'/sops/{sop}/publish?expected_revision=1', headers=owner)
        assert published.status_code == 201
        event = ws.receive_json()
        assert event['type'] == 'sop.published'
        assert event['version'] == 1
        assert event['sop_id'] == sop
    assert client.get(root + '/sops', headers=member).json()[0]['content']['title'] == 'Iced latte'
    assert client.put(root + f'/sops/{sop}?expected_revision=1', headers=owner, json=recipe('Hot latte')).status_code == 200
    assert client.get(root + '/sops', headers=member).json()[0]['content']['title'] == 'Iced latte'
    assert client.post(root + f'/sops/{sop}/publish?expected_revision=1', headers=owner).status_code == 409
    assert client.post(root + f'/sops/{sop}/publish?expected_revision=2', headers=owner).json()['version'] == 2
    # Identical publish retries do not emit another version/event.
    assert client.post(root + f'/sops/{sop}/publish?expected_revision=2', headers=owner).json()['version'] == 2
    versions = client.get(root + f'/sops/{sop}/versions', headers=member).json()
    assert [v['content']['title'] for v in versions] == ['Hot latte', 'Iced latte']
    with client.websocket_connect(root + f"/live?after={event['id']}") as ws:
        ws.send_json({'token': member['Authorization'].split()[1]})
        assert ws.receive_json()['type'] == 'ready'
        assert ws.receive_json()['version'] == 2
    assert len(client.get(root + '/events', headers=member).json()) == 2


def test_team_isolation_authorization_and_conflicts(client):
    owner, member, team = setup_team(client)
    outsider = account(client, 'outsider@example.com')
    root = f'/teams/{team}'
    sop = client.post(root + '/sops', headers=owner, json=recipe(category='food')).json()['id']
    assert client.get(root + '/sops').status_code == 401
    for path in ['/sops', '/drafts', '/events', f'/sops/{sop}/versions']:
        assert client.get(root + path, headers=outsider).status_code == 404
    assert client.post(root + '/invitations', headers=member).status_code == 403
    assert client.put(root + f'/sops/{sop}?expected_revision=1', headers=member, json=recipe()).status_code == 403
    assert client.post(root + f'/sops/{sop}/publish?expected_revision=1', headers=member).status_code == 403
    assert client.post(root + f'/sops/{sop}/publish?expected_revision=1', headers=outsider).status_code == 404
    assert client.put(root + f'/sops/{sop}?expected_revision=1', headers=owner, json=recipe()).status_code == 200
    assert client.put(root + f'/sops/{sop}?expected_revision=1', headers=owner, json=recipe()).status_code == 409
    with client.websocket_connect(root + '/live') as ws:
        ws.send_json({'token': outsider['Authorization'].split()[1]})
        assert ws.receive()['code'] == 4403


def test_authentication_validation_and_invitation_reuse(client):
    owner = account(client, 'owner@example.com')
    body = {'email': 'OWNER@example.com', 'password': 'correct-horse-battery'}
    assert client.post('/auth/register', json=body).status_code == 409
    assert client.post('/auth/login', json={**body, 'password': 'wrong-password'}).status_code == 401
    assert client.post('/auth/register', json={**body, 'password': 'short'}).status_code == 422
    assert client.post('/auth/register', json={**body, 'email': 'invalid'}).status_code == 422
    team = client.post('/teams', headers=owner, json={'name': 'Cafe'}).json()['id']
    token = client.post(f'/teams/{team}/invitations', headers=owner).json()['invitation_token']
    member = account(client, 'member@example.com')
    assert client.post('/teams/join', headers=member, json={'invitation_token': token}).status_code == 200
    assert client.post('/teams/join', headers=member, json={'invitation_token': token}).status_code == 400
    for payload in [{**recipe(), 'category': 'other'}, {**recipe(), 'steps': [' ']}, {**recipe(), 'ingredients': []}, {**recipe(), 'title': ' '}]:
        assert client.post(f'/teams/{team}/sops', headers=owner, json=payload).status_code == 422
    assert client.post('/auth/logout', headers=owner).status_code == 204
    assert client.get('/auth/me', headers=owner).status_code == 401
    with client.websocket_connect(f'/teams/{team}/live') as ws:
        ws.send_json({'token': owner['Authorization'].split()[1]})
        assert ws.receive()['code'] == 4401


def test_events_persist_across_application_restart(client):
    owner, member, team = setup_team(client)
    root = f'/teams/{team}'
    sop = client.post(root + '/sops', headers=owner, json=recipe()).json()['id']
    client.post(root + f'/sops/{sop}/publish?expected_revision=1', headers=owner)
    with TestClient(app) as restarted:
        assert restarted.get(root + '/sops', headers=member).json()[0]['version'] == 1
        assert restarted.get(root + '/events', headers=member).json()[0]['sop_id'] == sop
