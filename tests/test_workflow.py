import sqlite3
import pytest
from fastapi.testclient import TestClient
from app.main import app, database
from app.costing import recipe_cost
from test_core import account, recipe


@pytest.fixture
def workflow(tmp_path, monkeypatch):
    monkeypatch.setenv('MYSOP_DB', str(tmp_path / 'workflow.sqlite3'))
    with TestClient(app) as client:
        owner = account(client, 'owner@workflow.test')
        supervisor = account(client, 'supervisor@workflow.test')
        staff = account(client, 'staff@workflow.test')
        team = client.post('/teams', headers=owner, json={'name': 'Kitchen'}).json()['id']
        for headers, role in [(supervisor, 'supervisor'), (staff, 'staff')]:
            token = client.post(f'/teams/{team}/invitations', headers=owner, json={'role': role}).json()['invitation_token']
            assert client.post('/teams/join', headers=headers, json={'invitation_token': token}).status_code == 200
            assert client.get('/teams', headers=headers).json()[0]['role'] == role
        yield client, owner, supervisor, staff, f'/teams/{team}'


def priced_recipe(title='Kitchen latte'):
    return {**recipe(title), 'servings': 2, 'currency': 'MYR', 'ingredients': [
        {'name': 'Milk', 'quantity': 200, 'unit': 'ml', 'pack_quantity': 1000, 'pack_cost': 8},
        {'name': 'Coffee', 'quantity': 20, 'unit': 'g', 'pack_quantity': 1000, 'pack_cost': 60}]}



def operational_recipe(title='Kitchen latte'):
    body = priced_recipe(title)
    body.pop('currency')
    for ingredient in body['ingredients']:
        ingredient.pop('pack_quantity')
        ingredient.pop('pack_cost')
    return body


def test_supervisor_submission_owner_approval_cost_and_acknowledgment(workflow):
    c, owner, supervisor, staff, root = workflow
    sop = c.post(root + '/sops', headers=supervisor, json=operational_recipe()).json()['id']
    assert c.post(root + f'/sops/{sop}/publish?expected_revision=1', headers=supervisor).status_code == 403
    sub = c.post(root + f'/sops/{sop}/submit?expected_revision=1', headers=supervisor).json()['id']
    assert c.post(root + f'/sops/{sop}/submit?expected_revision=1', headers=supervisor).json()['id'] == sub
    assert c.get(root + '/sops', headers=staff).json() == []
    assert c.put(root + f'/sops/{sop}?expected_revision=1', headers=supervisor, json=operational_recipe('changed')).status_code == 409
    assert c.get(root + '/drafts', headers=supervisor).json()[0]['status'] == 'pending'
    queue = c.get(root + '/submissions', headers=owner).json()
    assert 'costing' not in queue[0]
    assert c.put(root + f'/sops/{sop}/bom?expected_revision=0', headers=owner, json={
        'currency': 'MYR', 'prices': [{k: i[k] for k in ('name', 'unit', 'pack_quantity', 'pack_cost')} for i in priced_recipe()['ingredients']]
    }).status_code == 200
    bill = c.get(root + f'/sops/{sop}/bom', headers=owner).json()
    assert bill['costing']['total'] == '2.80'
    assert bill['costing']['per_serving'] == '1.40'
    assert c.post(root + f'/submissions/{sub}/approve', headers=supervisor).status_code == 403
    assert c.post(root + f'/submissions/{sub}/approve', headers=owner).json()['version'] == 1
    assert c.post(root + f'/submissions/{sub}/approve', headers=owner).status_code == 409
    assert c.get(root + '/submissions', headers=owner).json() == []
    published = c.get(root + '/sops', headers=staff).json()[0]
    assert 'costing' not in published
    assert all('pack_cost' not in i for i in published['content']['ingredients'])
    assert published['acknowledged_at'] is None
    ack = root + f'/sops/{sop}/versions/1/acknowledge'
    assert c.post(ack, headers=staff).status_code == 200
    timestamp = c.get(root + '/sops', headers=staff).json()[0]['acknowledged_at']
    assert c.post(ack, headers=staff).status_code == 200
    assert c.get(root + '/sops', headers=staff).json()[0]['acknowledged_at'] == timestamp
    report = c.get(root + f'/sops/{sop}/acknowledgments', headers=owner).json()
    assert next(m for m in report['members'] if m['role'] == 'staff')['acknowledged_at'] == timestamp
    # A new approval retains immutable history and requires a fresh acknowledgment.
    assert c.put(root + f'/sops/{sop}?expected_revision=1', headers=supervisor, json=operational_recipe('Latte v2')).status_code == 200
    sub2 = c.post(root + f'/sops/{sop}/submit?expected_revision=2', headers=supervisor).json()['id']
    c.post(root + f'/submissions/{sub2}/approve', headers=owner)
    current = c.get(root + '/sops', headers=staff).json()[0]
    assert current['version'] == 2 and current['acknowledged_at'] is None
    assert c.get(root + f'/sops/{sop}/versions', headers=staff).json()[1]['content']['title'] == 'Kitchen latte'


def test_returned_submission_requires_revision_and_keeps_owner_notes(workflow):
    c, owner, supervisor, staff, root = workflow
    sop = c.post(root + '/sops', headers=supervisor, json=operational_recipe()).json()['id']
    sub = c.post(root + f'/sops/{sop}/submit?expected_revision=1', headers=supervisor).json()['id']
    assert c.post(root + f'/submissions/{sub}/return', headers=owner, json={'note': ' '}).status_code == 422
    assert c.post(root + f'/submissions/{sub}/return', headers=owner, json={'note': 'Specify milk storage temperature.'}).status_code == 200
    draft = c.get(root + '/drafts', headers=supervisor).json()[0]
    assert draft['status'] == 'changes_requested' and 'temperature' in draft['review_note']
    assert c.get(root + '/sops', headers=staff).json() == []
    assert c.post(root + f'/sops/{sop}/submit?expected_revision=1', headers=supervisor).status_code == 409
    assert c.put(root + f'/sops/{sop}?expected_revision=1', headers=supervisor, json=operational_recipe()).status_code == 200
    assert c.post(root + f'/sops/{sop}/submit?expected_revision=1', headers=supervisor).status_code == 409
    assert c.post(root + f'/sops/{sop}/submit?expected_revision=2', headers=supervisor).status_code == 201


def test_role_boundaries_cross_team_review_and_invalid_versions(workflow):
    c, owner, supervisor, staff, root = workflow
    assert c.post(root + '/sops', headers=staff, json=priced_recipe()).status_code == 403
    assert c.get(root + '/submissions', headers=staff).status_code == 403
    assert c.get(root + '/submissions', headers=supervisor).status_code == 403
    assert c.post(root + '/invitations', headers=owner, json={'role': 'owner'}).status_code == 422
    sop = c.post(root + '/sops', headers=supervisor, json=operational_recipe()).json()['id']
    assert c.post(root + f'/sops/{sop}/submit?expected_revision=1', headers=staff).status_code == 403
    sub = c.post(root + f'/sops/{sop}/submit?expected_revision=1', headers=supervisor).json()['id']
    other = c.post('/teams', headers=owner, json={'name': 'Other'}).json()['id']
    assert c.post(f'/teams/{other}/submissions/{sub}/approve', headers=owner).status_code == 404
    assert c.post(root + f'/sops/{sop}/versions/99/acknowledge', headers=staff).status_code == 404
    assert c.get(root + f'/sops/{sop}/acknowledgments', headers=staff).status_code == 403
    assert c.get(root + f'/sops/{sop}/acknowledgments', headers=owner).status_code == 404
    outsider = account(c, 'outsider@workflow.test')
    assert c.post(root + f'/sops/{sop}/versions/1/acknowledge', headers=outsider).status_code == 404


def test_prices_validate_and_missing_cost_is_not_reported_as_zero(workflow):
    c, owner, _, _, root = workflow
    for fields in [{'pack_cost': -1, 'pack_quantity': 1000}, {'pack_cost': 1, 'pack_quantity': 0}, {'pack_cost': 1}, {'pack_quantity': 1000}, {'pack_quantity': 1, 'pack_cost': 'NaN'}]:
        body = {**recipe(), 'ingredients': [{'name': 'Milk', 'quantity': 200, 'unit': 'ml', **fields}]}
        assert c.post(root + '/sops', headers=owner, json=body).status_code == 422
    cost = recipe_cost(recipe())
    assert cost['total'] is None and cost['per_serving'] is None and cost['missing_prices'] == 1
    body = priced_recipe()
    body['ingredients'][0]['pack_cost'] = 0
    assert recipe_cost(body)['total'] == '1.20'


def test_decimal_costs_round_after_summing():
    content = {**recipe(), 'servings': 3, 'ingredients': [
        {'name': 'A', 'quantity': '1', 'unit': 'g', 'pack_quantity': '3', 'pack_cost': '1'},
        {'name': 'B', 'quantity': '2', 'unit': 'g', 'pack_quantity': '3', 'pack_cost': '1'}]}
    assert recipe_cost(content)['total'] == '1.00'
    assert recipe_cost(content)['per_serving'] == '0.33'


def test_additive_legacy_database_upgrade(tmp_path, monkeypatch):
    path = tmp_path / 'legacy.sqlite3'
    with sqlite3.connect(path) as db:
        db.executescript("CREATE TABLE invites(token TEXT PRIMARY KEY, team_id TEXT, expires REAL NOT NULL); CREATE TABLE members(team_id TEXT,user_id TEXT,role TEXT NOT NULL,PRIMARY KEY(team_id,user_id)); INSERT INTO members VALUES('legacy-team','legacy-user','member'); INSERT INTO invites VALUES('legacy-invite','legacy-team',0);")
    monkeypatch.setenv('MYSOP_DB', str(path))
    for _ in range(2):
        with TestClient(app):
            with database() as db:
                assert db.execute('SELECT role FROM members').fetchone()['role'] == 'staff'
                assert db.execute('SELECT role FROM invites').fetchone()['role'] == 'staff'
                assert db.execute('PRAGMA user_version').fetchone()[0] == 4


def test_owner_can_promote_existing_staff_and_cannot_demote_owner(workflow):
    c, owner, supervisor, staff, root = workflow
    staff_id = c.get('/auth/me', headers=staff).json()['id']
    owner_id = c.get('/auth/me', headers=owner).json()['id']
    assert c.get(root + '/members', headers=staff).status_code == 403
    assert c.patch(root + f'/members/{staff_id}', headers=supervisor, json={'role': 'supervisor'}).status_code == 403
    assert c.patch(root + f'/members/{owner_id}', headers=owner, json={'role': 'staff'}).status_code == 403
    assert c.patch(root + f'/members/{staff_id}', headers=owner, json={'role': 'supervisor'}).status_code == 200
    assert c.post(root + '/sops', headers=staff, json=recipe()).status_code == 201
    assert c.patch(root + f'/members/{staff_id}', headers=owner, json={'role': 'staff'}).status_code == 200
    assert c.post(root + '/sops', headers=staff, json=recipe()).status_code == 403
