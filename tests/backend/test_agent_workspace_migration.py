"""Upgrade real account-owned records without discarding their history."""
from pathlib import Path
import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import MetaData, inspect, text
from app.shared.config import Config
from app.shared.db import make_engine, migrate


def test_account_owned_agent_history_survives_upgrade_and_rollback(tmp_path):
    config = Config(var_root=tmp_path)
    config.prepare()
    engine = make_engine(config)
    migration = AlembicConfig()
    migration.set_main_option('script_location', str(Path(__file__).resolve().parents[2] / 'backend/alembic'))
    with engine.begin() as connection:
        migration.attributes['connection'] = connection
        command.upgrade(migration, '0003_agent_workflow')
        metadata = MetaData()
        metadata.reflect(connection)
        records = {
            'users': dict(id='old-user', username='existing', password_hash='existing-hash', role='admin'),
            'agents': dict(id='agent', name='Existing agent', description='keep', owner_id='old-user', row_version=7, created_at='before', updated_at='before'),
            'agent_revisions': dict(id='revision', agent_id='agent', revision_no=1, state='published', config={'channels': []}, row_version=3, created_at='before', updated_at='before'),
            'agent_commands': dict(id='command', actor_id='old-user', command_key='retry', request_hash='hash', response={'id': 'agent'}, created_at='before'),
            'agent_validations': dict(id='validation', revision_id='revision', config_hash='hash', source_hash='source', capability_fingerprint='cap', verdict='executable', result={}, data_origin='real', created_at='before', expires_at='later'),
            'agent_confirmations': dict(id='confirmation', revision_id='revision', validation_id='validation', actor_id='old-user', config_hash='hash', limitations_acknowledged=True, created_at='before'),
        }
        for table, row in records.items():
            connection.execute(metadata.tables[table].insert().values(**row))
        before = {name: connection.execute(text(f'SELECT * FROM {name}')).fetchall() for name in records}

    migrate(engine)
    # A second startup must be harmless.
    migrate(engine)
    with engine.begin() as connection:
        for name in records:
            assert connection.execute(text(f'SELECT * FROM {name}')).fetchall() == before[name]
        for name in ('agents', 'agent_commands', 'agent_confirmations'):
            assert not any(fk['referred_table'] == 'users' for fk in inspect(connection).get_foreign_keys(name))
        assert connection.exec_driver_sql('PRAGMA foreign_key_check').fetchall() == []
        assert connection.exec_driver_sql('PRAGMA foreign_keys').scalar() == 1
        migration.attributes['connection'] = connection
        command.downgrade(migration, '0003_agent_workflow')
        for name in records:
            assert connection.execute(text(f'SELECT * FROM {name}')).fetchall() == before[name]
    migrate(engine)
    with engine.begin() as connection:
        connection.execute(text("UPDATE agents SET owner_id='workspace' WHERE id='agent'"))
    with pytest.raises(RuntimeError, match='pre-upgrade backup'):
        with engine.begin() as connection:
            migration.attributes['connection'] = connection
            command.downgrade(migration, '0003_agent_workflow')
    with engine.connect() as connection:
        assert connection.execute(text('SELECT version_num FROM alembic_version')).scalar() == '0006_requirement_plans'
        assert connection.execute(text("SELECT owner_id FROM agents WHERE id='agent'")).scalar() == 'workspace'
    engine.dispose()
