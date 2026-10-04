"""Run real SQL twice in disposable loopback PostgreSQL databases.

Set ZAUQ_TEST_POSTGRES_DSN to the admin DSN of a disposable local cluster.
The fresh-schema test additionally needs pgvector (provided by the CI image).
"""
import os
import subprocess
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest

ROOT = Path(__file__).resolve().parents[2]


def sql(dsn, statement):
    result = subprocess.run(['psql',dsn,'-X','-v','ON_ERROR_STOP=1','-At'],input=statement,text=True,capture_output=True,timeout=30)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


@pytest.fixture
def database():
    dsn = os.environ.get('ZAUQ_TEST_POSTGRES_DSN')
    if not dsn:
        pytest.skip('Disposable PostgreSQL cluster not configured')
    parsed = urlsplit(dsn)
    assert parsed.hostname in ('127.0.0.1','localhost','::1'), 'Test database must be loopback'
    name = 'zauq_test_' + uuid.uuid4().hex[:12]
    sql(dsn, "DO $$ BEGIN IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='anon') THEN CREATE ROLE anon; END IF; IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='authenticated') THEN CREATE ROLE authenticated; END IF; IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='service_role') THEN CREATE ROLE service_role BYPASSRLS; END IF; END $$;")
    sql(dsn, f'CREATE DATABASE {name};')
    test_dsn = urlunsplit(parsed._replace(path='/'+name))
    try:
        yield test_dsn
    finally:
        sql(dsn,f'DROP DATABASE {name} WITH (FORCE);')


@pytest.mark.parametrize('legacy_boolean',[False,True])
def test_existing_install_migrations_twice(database, legacy_boolean):
    sql(database, '''CREATE TABLE guild_configs(guild_id TEXT PRIMARY KEY,guild_name TEXT NOT NULL,default_provider TEXT DEFAULT 'gemini');
CREATE TABLE channel_profiles(channel_id TEXT PRIMARY KEY,guild_id TEXT REFERENCES guild_configs(guild_id),allow_code_exec BOOLEAN DEFAULT FALSE);
CREATE TABLE model_selection(channel_id TEXT PRIMARY KEY,provider TEXT CHECK(provider IN ('gemini','digitalocean','ollama','kaggle')));
CREATE TABLE request_logs(guild_id TEXT,channel_id TEXT,user_id TEXT,tier INT,provider TEXT,model_name TEXT,response_time_ms INT);
INSERT INTO guild_configs VALUES ('g','test','gemini');
INSERT INTO channel_profiles VALUES ('c','g',false);''')
    if legacy_boolean:
        sql(database, "ALTER TABLE channel_profiles ADD COLUMN auto_code_test_mode BOOLEAN DEFAULT FALSE; UPDATE channel_profiles SET auto_code_test_mode=TRUE;")
    for _ in range(2):
        for migration in sorted((ROOT/'backend/memory/migrations').glob('*.sql')):
            sql(database,migration.read_text())
    assert sql(database,"SELECT auto_code_test_mode FROM channel_profiles WHERE channel_id='c'") == ('auto' if legacy_boolean else 'off')
    assert sql(database,"SELECT allow_code_exec FROM channel_profiles WHERE channel_id='c'") == 'f'
    sql(database,"INSERT INTO model_selection VALUES('c','anthropic'); INSERT INTO request_logs(guild_id,provider,response_time_ms,tool_steps,estimated_cost_usd) VALUES('g','anthropic',100,3,0.2);")
    assert sql(database,"SELECT v4_metrics_summary('g')->>'total_tool_steps'") == '3'
    assert sql(database,"SELECT relrowsecurity FROM pg_class WHERE relname='pending_actions'") == 't'
    assert sql(database,"SELECT has_function_privilege('authenticated','v4_metrics_summary(text)','execute')") == 'f'
    sql(database,'GRANT SELECT ON pending_actions TO authenticated;')
    assert sql(database,'SET ROLE authenticated; SELECT count(*) FROM pending_actions;').splitlines()[-1] == '0'
    sql(database,"INSERT INTO pending_actions(action_id,channel_id,user_id,tool_name,expires_at,signature) VALUES('00000000-0000-0000-0000-000000000001','c','u','test',NOW()+INTERVAL '1 minute','signed');")
    assert sql(database,"WITH changed AS (UPDATE pending_actions SET status='approved' WHERE action_id='00000000-0000-0000-0000-000000000001' AND status='pending' AND expires_at>NOW() RETURNING *) SELECT count(*) FROM changed") == '1'
    assert sql(database,"WITH changed AS (UPDATE pending_actions SET status='approved' WHERE action_id='00000000-0000-0000-0000-000000000001' AND status='pending' AND expires_at>NOW() RETURNING *) SELECT count(*) FROM changed") == '0'


def test_fresh_schema_twice(database):
    if sql(database,"SELECT count(*) FROM pg_available_extensions WHERE name='vector'") != '1':
        if os.environ.get('ZAUQ_REQUIRE_PGVECTOR') == 'true':
            pytest.fail('CI requires pgvector for the fresh schema gate')
        pytest.skip('pgvector unavailable in this local PostgreSQL installation')
    schema = (ROOT/'backend/memory/schema.sql').read_text()
    sql(database,schema)
    sql(database,schema)
    assert sql(database,"SELECT v4_metrics_summary(NULL)->>'total_requests'") == '0'
