"""MYSOP core: isolated teams, private drafts, immutable publications and durable events."""
import asyncio
import hashlib
import json
import os
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager, contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pwdlib import PasswordHash
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.costing import recipe_cost

passwords = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@contextmanager
def database():
    path = Path(os.environ.get('MYSOP_DB', 'data/mysop.sqlite3'))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app):
    with database() as db:
        db.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, password TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id), expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS teams(id TEXT PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS members(team_id TEXT REFERENCES teams(id), user_id TEXT REFERENCES users(id), role TEXT NOT NULL, PRIMARY KEY(team_id,user_id));
        CREATE TABLE IF NOT EXISTS invites(token TEXT PRIMARY KEY, team_id TEXT REFERENCES teams(id), expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS sops(id TEXT PRIMARY KEY, team_id TEXT REFERENCES teams(id), author_id TEXT REFERENCES users(id), draft TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS publications(sop_id TEXT REFERENCES sops(id), version INTEGER, content TEXT NOT NULL, published_at REAL NOT NULL, publisher_id TEXT REFERENCES users(id), PRIMARY KEY(sop_id,version));
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT, team_id TEXT REFERENCES teams(id), payload TEXT NOT NULL);
        ''')
        # Additive upgrade of the existing 0.2 database; retain every SOP/version.
        if 'role' not in {row['name'] for row in db.execute('PRAGMA table_info(invites)')}:
            db.execute("ALTER TABLE invites ADD COLUMN role TEXT NOT NULL DEFAULT 'staff'")
        db.execute("UPDATE members SET role='staff' WHERE role='member'")
        db.executescript('''CREATE TABLE IF NOT EXISTS submissions(
            id TEXT PRIMARY KEY, sop_id TEXT REFERENCES sops(id), revision INTEGER NOT NULL,
            content TEXT NOT NULL, submitted_by TEXT REFERENCES users(id), submitted_at REAL NOT NULL,
            status TEXT NOT NULL, review_note TEXT NOT NULL DEFAULT '', reviewer_id TEXT REFERENCES users(id),
            reviewed_at REAL, UNIQUE(sop_id,revision));
            CREATE TABLE IF NOT EXISTS acknowledgments(
            sop_id TEXT, version INTEGER, user_id TEXT REFERENCES users(id), acknowledged_at REAL NOT NULL,
            PRIMARY KEY(sop_id,version,user_id), FOREIGN KEY(sop_id,version) REFERENCES publications(sop_id,version));
            CREATE INDEX IF NOT EXISTS events_team_cursor ON events(team_id,id);
            CREATE INDEX IF NOT EXISTS submissions_sop ON submissions(sop_id,revision);
            PRAGMA user_version=3;''')
    yield


app = FastAPI(title='MYSOP', version='0.3.0', lifespan=lifespan)
STATIC_DIR = Path(__file__).parent / 'static'
app.mount('/static', StaticFiles(directory=STATIC_DIR), name='static')


@app.get('/', include_in_schema=False)
def web_app():
    return FileResponse(STATIC_DIR / 'index.html')


class Model(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Credentials(Model):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=10, max_length=128)

    @field_validator('email')
    @classmethod
    def normalize_email(cls, value):
        value = value.lower()
        if value.count('@') != 1 or not all(value.split('@')) or any(c.isspace() for c in value):
            raise ValueError('Enter a valid email address')
        return value


class TeamInput(Model):
    name: str = Field(min_length=1, max_length=120)


class JoinInput(Model):
    invitation_token: str = Field(min_length=20, max_length=200)


class InvitationInput(Model):
    role: Literal['staff', 'supervisor'] = 'staff'


class RoleInput(Model):
    role: Literal['staff', 'supervisor']


class ReviewInput(Model):
    note: str = Field(min_length=1, max_length=2000)


class Ingredient(Model):
    name: str = Field(min_length=1, max_length=160)
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=4, allow_inf_nan=False)
    unit: str = Field(min_length=1, max_length=40)
    pack_quantity: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=4, allow_inf_nan=False)
    pack_cost: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=4, allow_inf_nan=False)

    @model_validator(mode='after')
    def paired_price(self):
        if (self.pack_quantity is None) != (self.pack_cost is None):
            raise ValueError('Supply both pack quantity and pack cost, or leave both blank')
        return self


class SOPInput(Model):
    title: str = Field(min_length=1, max_length=160)
    category: Literal['food', 'drink']
    description: str = Field(default='', max_length=4000)
    servings: int = Field(default=1, ge=1, le=10000)
    currency: Literal['MYR', 'SGD', 'USD', 'EUR', 'GBP'] = 'MYR'
    ingredients: list[Ingredient] = Field(min_length=1, max_length=100)
    steps: list[str] = Field(min_length=1, max_length=100)
    allergens: list[str] = Field(default_factory=list, max_length=50)
    safety_notes: str = Field(default='', max_length=4000)

    @field_validator('steps', 'allergens')
    @classmethod
    def nonempty_entries(cls, values):
        if any(not v.strip() or len(v) > 2000 for v in values):
            raise ValueError('Entries must contain 1–2000 characters')
        return [v.strip() for v in values]


def authenticated(token):
    with database() as db:
        user = db.execute('SELECT users.id, users.email FROM sessions JOIN users ON users.id=sessions.user_id WHERE token=? AND expires>?', (digest(token), time.time())).fetchone()
    if not user:
        raise HTTPException(401, 'Invalid or expired session')
    return dict(user)


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if not credentials or credentials.scheme.lower() != 'bearer':
        raise HTTPException(401, 'Bearer authentication required')
    return authenticated(credentials.credentials)


def membership(db, team_id, user_id, owner=False):
    row = db.execute('SELECT role FROM members WHERE team_id=? AND user_id=?', (team_id, user_id)).fetchone()
    if not row:
        raise HTTPException(404, 'Team not found')
    if owner and row['role'] != 'owner':
        raise HTTPException(403, 'Team owner required')
    return row['role']


def authoring(db, team_id, user_id):
    role = membership(db, team_id, user_id)
    if role not in ('owner', 'supervisor'):
        raise HTTPException(403, 'Owner or supervisor required')
    return role


def find_sop(db, team_id, sop_id, user_id, author=False):
    membership(db, team_id, user_id)
    row = db.execute('SELECT * FROM sops WHERE id=? AND team_id=?', (sop_id, team_id)).fetchone()
    if not row:
        raise HTTPException(404, 'SOP not found')
    if author and row['author_id'] != user_id:
        raise HTTPException(403, 'Only the author can edit or publish this draft')
    return row


def publication(row):
    content = json.loads(row['content'])
    return dict(sop_id=row['sop_id'], version=row['version'], content=content,
                published_at=row['published_at'], publisher_id=row['publisher_id'], costing=recipe_cost(content))


def emit(db, team_id, payload):
    return db.execute('INSERT INTO events(team_id,payload) VALUES(?,?)', (team_id, json.dumps(payload))).lastrowid


def publish_snapshot(db, sop_id, team_id, content, user_id):
    existing = db.execute('SELECT * FROM publications WHERE sop_id=? ORDER BY version DESC LIMIT 1', (sop_id,)).fetchone()
    if existing and existing['content'] == content:
        return publication(existing)
    version = existing['version'] + 1 if existing else 1
    published_at = time.time()
    db.execute('INSERT INTO publications VALUES(?,?,?,?,?)', (sop_id, version, content, published_at, user_id))
    payload = {'type': 'sop.published', 'sop_id': sop_id, 'version': version, 'published_at': published_at}
    return {**payload, 'event_id': emit(db, team_id, payload)}


def draft_record(db, row):
    submission = db.execute('SELECT status, review_note FROM submissions WHERE sop_id=? AND revision=?', (row['id'], row['revision'])).fetchone()
    return {'id': row['id'], 'revision': row['revision'], 'content': json.loads(row['draft']),
            'status': submission['status'] if submission else 'draft',
            'review_note': submission['review_note'] if submission else ''}



@app.get('/health')
def health():
    with database() as db:
        db.execute('SELECT 1')
    return {'status': 'ok'}


@app.post('/auth/register', status_code=201)
def register(body: Credentials):
    user_id = str(uuid4())
    password_hash = passwords.hash(body.password)
    try:
        with database() as db:
            db.execute('INSERT INTO users VALUES(?,?,?)', (user_id, body.email, password_hash))
    except sqlite3.IntegrityError:
        raise HTTPException(409, 'Email already registered')
    return {'id': user_id, 'email': body.email}


@app.post('/auth/login')
def login(body: Credentials):
    with database() as db:
        row = db.execute('SELECT * FROM users WHERE email=?', (body.email,)).fetchone()
        # Verify a dummy hash too, so unknown users still incur password-hashing cost.
        stored = row['password'] if row else DUMMY_PASSWORD
        valid = passwords.verify(body.password, stored)
        if not row or not valid:
            raise HTTPException(401, 'Invalid credentials')
        token = secrets.token_urlsafe(32)
        db.execute('INSERT INTO sessions VALUES(?,?,?)', (digest(token), row['id'], time.time() + 86400))
    return {'access_token': token, 'token_type': 'bearer', 'expires_in': 86400}


DUMMY_PASSWORD = passwords.hash(secrets.token_urlsafe(32))


@app.post('/auth/logout', status_code=204)
def logout(credentials: HTTPAuthorizationCredentials = Depends(bearer), user=Depends(current_user)):
    with database() as db:
        db.execute('DELETE FROM sessions WHERE token=?', (digest(credentials.credentials),))


@app.get('/auth/me')
def me(user=Depends(current_user)):
    return user


@app.post('/teams', status_code=201)
def create_team(body: TeamInput, user=Depends(current_user)):
    team_id = str(uuid4())
    with database() as db:
        db.execute('INSERT INTO teams VALUES(?,?)', (team_id, body.name))
        db.execute('INSERT INTO members VALUES(?,?,?)', (team_id, user['id'], 'owner'))
    return {'id': team_id, 'name': body.name, 'role': 'owner'}


@app.get('/teams')
def list_teams(user=Depends(current_user)):
    with database() as db:
        return [dict(r) for r in db.execute('SELECT teams.*,role FROM teams JOIN members ON teams.id=team_id WHERE user_id=? ORDER BY teams.name', (user['id'],))]


@app.post('/teams/{team_id}/invitations', status_code=201)
def invite(team_id: str, body: InvitationInput = InvitationInput(), user=Depends(current_user)):
    token = secrets.token_urlsafe(32)
    with database() as db:
        membership(db, team_id, user['id'], owner=True)
        db.execute('INSERT INTO invites(token,team_id,expires,role) VALUES(?,?,?,?)', (digest(token), team_id, time.time() + 86400, body.role))
    return {'invitation_token': token, 'expires_in': 86400}


@app.post('/teams/join')
def join(body: JoinInput, user=Depends(current_user)):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        invitation = db.execute('SELECT * FROM invites WHERE token=? AND expires>?', (digest(body.invitation_token), time.time())).fetchone()
        if not invitation:
            raise HTTPException(400, 'Invalid, used or expired invitation')
        team_id = invitation['team_id']
        db.execute('INSERT OR IGNORE INTO members VALUES(?,?,?)', (team_id, user['id'], invitation['role']))
        db.execute('DELETE FROM invites WHERE token=?', (digest(body.invitation_token),))
    return {'team_id': team_id}


@app.get('/teams/{team_id}/members')
def members(team_id: str, user=Depends(current_user)):
    with database() as db:
        membership(db, team_id, user['id'], owner=True)
        return [dict(r) for r in db.execute('SELECT u.id,u.email,m.role FROM members m JOIN users u ON u.id=m.user_id WHERE m.team_id=? ORDER BY u.email', (team_id,))]


@app.patch('/teams/{team_id}/members/{member_id}')
def change_role(team_id: str, member_id: str, body: RoleInput, user=Depends(current_user)):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        membership(db, team_id, user['id'], owner=True)
        member = db.execute('SELECT role FROM members WHERE team_id=? AND user_id=?', (team_id, member_id)).fetchone()
        if not member:
            raise HTTPException(404, 'Member not found')
        if member['role'] == 'owner':
            raise HTTPException(403, 'Owner role cannot be changed here')
        db.execute('UPDATE members SET role=? WHERE team_id=? AND user_id=?', (body.role, team_id, member_id))
        emit(db, team_id, {'type': 'team.role_changed', 'user_id': member_id})
    return {'id': member_id, 'role': body.role}


@app.post('/teams/{team_id}/sops', status_code=201)
def create_sop(team_id: str, body: SOPInput, user=Depends(current_user)):
    sop_id = str(uuid4())
    with database() as db:
        authoring(db, team_id, user['id'])
        db.execute('INSERT INTO sops(id,team_id,author_id,draft) VALUES(?,?,?,?)', (sop_id, team_id, user['id'], body.model_dump_json()))
    return {'id': sop_id, 'revision': 1, 'content': body.model_dump()}


@app.get('/teams/{team_id}/drafts')
def drafts(team_id: str, user=Depends(current_user)):
    with database() as db:
        membership(db, team_id, user['id'])
        return [draft_record(db, r) for r in db.execute('SELECT * FROM sops WHERE team_id=? AND author_id=?', (team_id, user['id']))]


@app.put('/teams/{team_id}/sops/{sop_id}')
def update_sop(team_id: str, sop_id: str, body: SOPInput, expected_revision: int = Query(ge=1), user=Depends(current_user)):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        authoring(db, team_id, user['id'])
        find_sop(db, team_id, sop_id, user['id'], author=True)
        if db.execute("SELECT 1 FROM submissions WHERE sop_id=? AND status='pending'", (sop_id,)).fetchone():
            raise HTTPException(409, 'This draft is awaiting owner review')
        result = db.execute('UPDATE sops SET draft=?,revision=revision+1 WHERE id=? AND revision=?', (body.model_dump_json(), sop_id, expected_revision))
        if result.rowcount != 1:
            raise HTTPException(409, 'Draft changed; reload before saving')
    return {'id': sop_id, 'revision': expected_revision + 1, 'content': body.model_dump()}


@app.post('/teams/{team_id}/sops/{sop_id}/publish', status_code=201)
def publish(team_id: str, sop_id: str, expected_revision: int = Query(ge=1), user=Depends(current_user)):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        sop = find_sop(db, team_id, sop_id, user['id'], author=True)
        if sop['revision'] != expected_revision:
            raise HTTPException(409, 'Draft changed; reload before publishing')
        membership(db, team_id, user['id'], owner=True)
        if db.execute("SELECT 1 FROM submissions WHERE sop_id=? AND status='pending'", (sop_id,)).fetchone():
            raise HTTPException(409, 'Use the approval queue to review this submitted draft')
        return publish_snapshot(db, sop_id, team_id, sop['draft'], user['id'])


@app.get('/teams/{team_id}/sops')
def published_sops(team_id: str, user=Depends(current_user)):
    with database() as db:
        membership(db, team_id, user['id'])
        rows = db.execute('SELECT p.* FROM publications p JOIN sops s ON s.id=p.sop_id WHERE s.team_id=? AND p.version=(SELECT MAX(version) FROM publications WHERE sop_id=p.sop_id)', (team_id,)).fetchall()
        result = []
        for row in rows:
            record = publication(row)
            acknowledged = db.execute('SELECT acknowledged_at FROM acknowledgments WHERE sop_id=? AND version=? AND user_id=?', (row['sop_id'], row['version'], user['id'])).fetchone()
            record['acknowledged_at'] = acknowledged['acknowledged_at'] if acknowledged else None
            result.append(record)
        return result


@app.get('/teams/{team_id}/sops/{sop_id}/versions')
def history(team_id: str, sop_id: str, user=Depends(current_user)):
    with database() as db:
        find_sop(db, team_id, sop_id, user['id'])
        return [publication(r) for r in db.execute('SELECT * FROM publications WHERE sop_id=? ORDER BY version DESC', (sop_id,))]


@app.post('/teams/{team_id}/sops/{sop_id}/submit', status_code=201)
def submit_draft(team_id: str, sop_id: str, expected_revision: int = Query(ge=1), user=Depends(current_user)):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        authoring(db, team_id, user['id'])
        sop = find_sop(db, team_id, sop_id, user['id'], author=True)
        if sop['revision'] != expected_revision:
            raise HTTPException(409, 'Draft changed; reload before submitting')
        existing = db.execute('SELECT * FROM submissions WHERE sop_id=? AND revision=?', (sop_id, expected_revision)).fetchone()
        if existing:
            if existing['status'] == 'pending':
                return {'id': existing['id'], 'status': 'pending'}
            raise HTTPException(409, 'Revise the draft before submitting it again')
        submission_id = str(uuid4())
        db.execute('INSERT INTO submissions(id,sop_id,revision,content,submitted_by,submitted_at,status) VALUES(?,?,?,?,?,?,?)',
                   (submission_id, sop_id, expected_revision, sop['draft'], user['id'], time.time(), 'pending'))
        emit(db, team_id, {'type': 'sop.submitted', 'sop_id': sop_id, 'submission_id': submission_id})
    return {'id': submission_id, 'status': 'pending'}


@app.get('/teams/{team_id}/submissions')
def review_queue(team_id: str, user=Depends(current_user)):
    with database() as db:
        membership(db, team_id, user['id'], owner=True)
        rows = db.execute("SELECT sub.*,u.email AS author_email FROM submissions sub JOIN sops s ON s.id=sub.sop_id JOIN users u ON u.id=sub.submitted_by WHERE s.team_id=? AND sub.status='pending' ORDER BY sub.submitted_at", (team_id,)).fetchall()
        return [{**dict(r), 'content': json.loads(r['content']), 'costing': recipe_cost(json.loads(r['content']))} for r in rows]


@app.post('/teams/{team_id}/submissions/{submission_id}/approve')
def approve(team_id: str, submission_id: str, user=Depends(current_user)):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        membership(db, team_id, user['id'], owner=True)
        sub = db.execute('SELECT sub.* FROM submissions sub JOIN sops s ON s.id=sub.sop_id WHERE sub.id=? AND s.team_id=?', (submission_id, team_id)).fetchone()
        if not sub:
            raise HTTPException(404, 'Submission not found')
        if sub['status'] != 'pending':
            raise HTTPException(409, 'Submission already reviewed')
        sop = find_sop(db, team_id, sub['sop_id'], user['id'])
        if sop['revision'] != sub['revision']:
            raise HTTPException(409, 'Submission no longer matches the draft')
        result = publish_snapshot(db, sub['sop_id'], team_id, sub['content'], user['id'])
        db.execute("UPDATE submissions SET status='approved',reviewer_id=?,reviewed_at=? WHERE id=?", (user['id'], time.time(), submission_id))
        emit(db, team_id, {'type': 'sop.reviewed', 'sop_id': sub['sop_id'], 'status': 'approved'})
        return result


@app.post('/teams/{team_id}/submissions/{submission_id}/return')
def return_draft(team_id: str, submission_id: str, body: ReviewInput, user=Depends(current_user)):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        membership(db, team_id, user['id'], owner=True)
        sub = db.execute('SELECT sub.* FROM submissions sub JOIN sops s ON s.id=sub.sop_id WHERE sub.id=? AND s.team_id=?', (submission_id, team_id)).fetchone()
        if not sub:
            raise HTTPException(404, 'Submission not found')
        if sub['status'] != 'pending':
            raise HTTPException(409, 'Submission already reviewed')
        db.execute("UPDATE submissions SET status='changes_requested',review_note=?,reviewer_id=?,reviewed_at=? WHERE id=?", (body.note, user['id'], time.time(), submission_id))
        emit(db, team_id, {'type': 'sop.reviewed', 'sop_id': sub['sop_id'], 'status': 'changes_requested'})
    return {'status': 'changes_requested'}


@app.post('/teams/{team_id}/sops/{sop_id}/versions/{version}/acknowledge')
def acknowledge(team_id: str, sop_id: str, version: int, user=Depends(current_user)):
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        find_sop(db, team_id, sop_id, user['id'])
        if not db.execute('SELECT 1 FROM publications WHERE sop_id=? AND version=?', (sop_id, version)).fetchone():
            raise HTTPException(404, 'Published version not found')
        result = db.execute('INSERT OR IGNORE INTO acknowledgments VALUES(?,?,?,?)', (sop_id, version, user['id'], time.time()))
        if result.rowcount:
            emit(db, team_id, {'type': 'sop.acknowledged', 'sop_id': sop_id, 'version': version})
    return {'status': 'acknowledged', 'version': version}


@app.get('/teams/{team_id}/sops/{sop_id}/acknowledgments')
def acknowledgment_report(team_id: str, sop_id: str, user=Depends(current_user)):
    with database() as db:
        role = membership(db, team_id, user['id'])
        if role not in ('owner', 'supervisor'):
            raise HTTPException(403, 'Owner or supervisor required')
        find_sop(db, team_id, sop_id, user['id'])
        version = db.execute('SELECT MAX(version) AS version FROM publications WHERE sop_id=?', (sop_id,)).fetchone()['version']
        if version is None:
            raise HTTPException(404, 'No published version')
        rows = db.execute('SELECT u.id,u.email,m.role,a.acknowledged_at FROM members m JOIN users u ON u.id=m.user_id LEFT JOIN acknowledgments a ON a.user_id=u.id AND a.sop_id=? AND a.version=? WHERE m.team_id=? ORDER BY u.email', (sop_id, version, team_id)).fetchall()
        return {'version': version, 'members': [dict(r) for r in rows]}


def events_for(team_id, user_id, after):
    with database() as db:
        membership(db, team_id, user_id)
        rows = db.execute('SELECT * FROM events WHERE team_id=? AND id>? ORDER BY id LIMIT 100', (team_id, after)).fetchall()
        return [{'id': r['id'], **json.loads(r['payload'])} for r in rows]


@app.get('/teams/{team_id}/events')
def events(team_id: str, after: int = Query(default=0, ge=0), user=Depends(current_user)):
    return events_for(team_id, user['id'], after)


@app.websocket('/teams/{team_id}/live')
async def live(websocket: WebSocket, team_id: str, after: int = Query(default=0, ge=0)):
    # Token is sent in the first frame, never exposed in URL/access logs.
    await websocket.accept()
    try:
        frame = await asyncio.wait_for(websocket.receive_json(), timeout=10)
        if not isinstance(frame, dict) or not isinstance(frame.get('token'), str):
            await websocket.close(code=4401)
            return
        token = frame['token']
        user = authenticated(token)
        events_for(team_id, user['id'], after)
        await websocket.send_json({'type': 'ready', 'after': after})
        while True:
            authenticated(token)  # Expiry/logout also revokes an existing connection.
            batch = events_for(team_id, user['id'], after)
            for event in batch:
                await websocket.send_json(event)
                after = event['id']
            try:
                message = await asyncio.wait_for(websocket.receive_text(), timeout=0.5)
                if message == 'ping':
                    await websocket.send_json({'type': 'pong'})
            except asyncio.TimeoutError:
                pass
    except HTTPException as exc:
        await websocket.close(code=4401 if exc.status_code == 401 else 4403)
    except (ValueError, asyncio.TimeoutError):
        await websocket.close(code=4401)
    except WebSocketDisconnect:
        pass
