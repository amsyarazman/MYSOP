import base64
from io import BytesIO
from random import Random

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app, database
from app.costing import recipe_cost
from test_core import account, recipe
from test_workflow import operational_recipe, priced_recipe, workflow


def bill_body():
    return {'currency': 'MYR', 'prices': [
        {k: i[k] for k in ('name', 'unit', 'pack_quantity', 'pack_cost')}
        for i in priced_recipe()['ingredients']
    ], 'other_costs': [{'name': 'Packaging', 'per_serving': '0.35'}, {'name': 'Labour', 'per_serving': '0.50'}]}


def assert_private(value):
    if isinstance(value, dict):
        assert not {'pack_quantity', 'pack_cost', 'costing', 'currency', 'other_costs'} & value.keys()
        for v in value.values():
            assert_private(v)
    elif isinstance(value, list):
        for v in value:
            assert_private(v)


def test_large_valid_costs_keep_the_last_cent():
    content = {'servings': 1, 'ingredients': [
        {'name': str(i), 'quantity': '9999999999.9999', 'unit': 'g',
         'pack_quantity': '0.0001', 'pack_cost': '9999999999.9999'} for i in range(100)
    ]}
    assert recipe_cost(content)['total'] == '99999999999998000000000000.01'


def test_owner_only_costs_per_serving_and_sop_privacy(workflow):
    c, owner, supervisor, staff, root = workflow
    sop = c.post(root + '/sops', headers=supervisor, json=operational_recipe()).json()['id']
    endpoint = root + f'/sops/{sop}/bom'
    for role in (supervisor, staff):
        assert c.get(endpoint, headers=role).status_code == 403
        assert c.put(endpoint + '?expected_revision=0', headers=role, json=bill_body()).status_code == 403
    assert c.get(endpoint).status_code == 401
    outsider = account(c, 'other-owner@example.test')
    c.post('/teams', headers=outsider, json={'name': 'Other kitchen'})
    assert c.get(endpoint, headers=outsider).status_code == 404
    assert c.put(endpoint + '?expected_revision=0', headers=outsider, json=bill_body()).status_code == 404
    assert c.post(root + '/sops', headers=supervisor, json=priced_recipe()).status_code == 403
    saved = c.put(endpoint + '?expected_revision=0', headers=owner, json=bill_body())
    assert saved.status_code == 200
    cost = saved.json()['costing']
    assert cost['ingredient_subtotal'] == '2.80'
    assert cost['other_per_serving'] == '0.85'
    assert cost['other_total'] == '1.70'
    assert cost['total'] == '4.50' and cost['per_serving'] == '2.25'
    assert c.put(endpoint + '?expected_revision=0', headers=owner, json=bill_body()).status_code == 409
    sub = c.post(root + f'/sops/{sop}/submit?expected_revision=1', headers=supervisor).json()['id']
    assert_private(c.get(root + '/drafts', headers=supervisor).json())
    assert_private(c.get(root + '/submissions', headers=owner).json())
    c.post(root + f'/submissions/{sub}/approve', headers=owner)
    for headers in (owner, supervisor, staff):
        assert_private(c.get(root + '/sops', headers=headers).json())
        assert_private(c.get(root + f'/sops/{sop}/versions', headers=headers).json())
        assert_private(c.get(root + '/events', headers=headers).json())
    c.post(root + f'/sops/{sop}/versions/1/acknowledge', headers=staff)
    # A price update affects neither SOP version nor the existing acknowledgment.
    updated = bill_body()
    updated['other_costs'][0]['per_serving'] = '0.45'
    assert c.put(endpoint + '?version=1&expected_revision=1', headers=owner, json=updated).status_code == 200
    published = c.get(root + '/sops', headers=staff).json()[0]
    assert published['version'] == 1 and published['acknowledged_at'] is not None
    changed = operational_recipe()
    changed['ingredients'][0]['quantity'] = 400
    assert c.put(root + f'/sops/{sop}?expected_revision=1', headers=supervisor, json=changed).status_code == 200
    assert c.get(endpoint, headers=owner).json()['costing']['total'] == '6.30'
    assert c.get(endpoint + '?version=1', headers=owner).json()['costing']['total'] == '4.70'
    assert c.get(endpoint + '?version=999', headers=owner).status_code == 404


@pytest.mark.parametrize('change', [
    {'other_costs': [{'name': 'Labour', 'per_serving': '-1'}]},
    {'other_costs': [{'name': 'Labour', 'per_serving': 'NaN'}]},
    {'other_costs': [{'name': ' ', 'per_serving': 0}]},
    {'prices': [{'name': 'Milk', 'unit': 'ml', 'pack_quantity': 0, 'pack_cost': 1}]},
    {'prices': [{'name': 'Milk', 'unit': 'ml', 'pack_cost': 1}]},
    {'prices': [{'name': 'Milk', 'unit': 'ml'}, {'name': 'Milk', 'unit': 'ml'}]},
])
def test_invalid_bom_rejected(workflow, change):
    c, owner, _, _, root = workflow
    sop = c.post(root + '/sops', headers=owner, json=recipe()).json()['id']
    assert c.put(root + f'/sops/{sop}/bom?expected_revision=0', headers=owner, json={**bill_body(), **change}).status_code == 422


def test_missing_prices_and_zero_extra_cost(workflow):
    c, owner, _, _, root = workflow
    sop = c.post(root + '/sops', headers=owner, json=recipe()).json()['id']
    endpoint = root + f'/sops/{sop}/bom'
    cost = c.put(endpoint + '?expected_revision=0', headers=owner, json={'other_costs': [{'name': 'Packaging', 'per_serving': 0}]}).json()['costing']
    assert cost['total'] is None and cost['per_serving'] is None
    assert cost['missing_prices'] == 1 and cost['other_per_serving'] == '0.00'


def photo(width=512, height=512):
    output = BytesIO()
    metadata = Image.Exif()
    metadata[0x010F] = 'Private camera metadata'
    Image.new('RGB', (width, height), '#526c49').save(output, 'JPEG', exif=metadata)
    return 'data:image/jpeg;base64,' + base64.b64encode(output.getvalue()).decode()


def test_photo_and_staff_measure_survive_publication_and_restart(workflow):
    c, owner, _, staff, root = workflow
    body = {**recipe(), 'photo_data_url': photo()}
    body['ingredients'][0]['measure_note'] = 'Fill cup to Line A'
    response = c.post(root + '/sops', headers=owner, json=body)
    assert response.status_code == 201
    sop = response.json()['id']
    c.post(root + f'/sops/{sop}/publish?expected_revision=1', headers=owner)
    with TestClient(app) as restarted:
        content = restarted.get(root + '/sops', headers=staff).json()[0]['content']
        assert content['ingredients'][0]['measure_note'] == 'Fill cup to Line A'
        raw = base64.b64decode(content['photo_data_url'].split(',')[1])
        assert len(raw) <= 150_000
        with Image.open(BytesIO(raw)) as image:
            assert image.size == (512, 512) and image.format == 'JPEG'
            assert not image.getexif()
    body['photo_data_url'] = None
    assert c.put(root + f'/sops/{sop}?expected_revision=1', headers=owner, json=body).json()['content']['photo_data_url'] is None


@pytest.mark.parametrize('value', [photo(400, 300), photo(513, 513), 'data:image/svg+xml,<svg/>', 'data:image/jpeg;base64,bad!', 'data:image/jpeg;base64,' + base64.b64encode(b'x' * 150_001).decode()])
def test_invalid_photos_rejected(workflow, value):
    c, owner, _, _, root = workflow
    assert c.post(root + '/sops', headers=owner, json={**recipe(), 'photo_data_url': value}).status_code == 422


def test_detailed_photo_remains_below_storage_limit(workflow):
    c, owner, _, _, root = workflow
    output = BytesIO()
    Image.frombytes('RGB', (512, 512), Random(4).randbytes(512 * 512 * 3)).save(output, 'JPEG', quality=55)
    value = 'data:image/jpeg;base64,' + base64.b64encode(output.getvalue()).decode()
    result = c.post(root + '/sops', headers=owner, json={**recipe(), 'photo_data_url': value})
    assert result.status_code == 201
    assert len(base64.b64decode(result.json()['content']['photo_data_url'].split(',')[1])) <= 150_000


def test_legacy_price_migration_keeps_history_and_saved_bom(workflow):
    c, owner, supervisor, staff, root = workflow
    sop = c.post(root + '/sops', headers=owner, json=priced_recipe()).json()['id']
    c.post(root + f'/sops/{sop}/publish?expected_revision=1', headers=owner)
    with database() as db:
        before = db.execute('SELECT content FROM publications WHERE sop_id=?', (sop,)).fetchone()[0]
        db.execute('DROP TABLE bills_of_materials')
    with TestClient(app) as restarted:
        endpoint = root + f'/sops/{sop}/bom'
        legacy = restarted.get(endpoint, headers=owner).json()
        assert legacy['costing']['total'] == '2.80'
        assert_private(restarted.get(root + f'/sops/{sop}/versions', headers=supervisor).json())
        assert restarted.put(endpoint + '?expected_revision=1', headers=owner, json=bill_body()).status_code == 200
    with TestClient(app) as restarted:
        assert restarted.get(endpoint, headers=owner).json()['costing']['total'] == '4.50'
        with database() as db:
            assert db.execute('SELECT content FROM publications WHERE sop_id=?', (sop,)).fetchone()[0] == before
