"""Remove account foreign keys while retaining historical actor identifiers.

No user, session, agent, revision or receipt rows are deleted. Rollback after
workspace writes requires restoring the pre-upgrade database backup.
"""
from alembic import op
import sqlalchemy as sa

revision = '0004_workspace_actors'
down_revision = '0003_agent_workflow'
branch_labels = None
depends_on = None

ACTORS = [('agents', 'owner_id'), ('agent_commands', 'actor_id'),
          ('agent_confirmations', 'actor_id')]
NAMING = {'fk': 'fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s'}


def rebuild(restore=False):
    connection = op.get_bind()
    # sqlite3 legacy transaction control does not begin a real transaction for
    # DDL/reflection. Begin explicitly so deferral survives those statements.
    if not connection.connection.driver_connection.in_transaction:
        connection.exec_driver_sql('BEGIN IMMEDIATE')
    # Recreating agents temporarily removes a referenced parent table. Defer
    # enforcement until every table is restored, then check the entire graph.
    connection.exec_driver_sql('PRAGMA defer_foreign_keys=ON')
    for table, column in ACTORS:
        with op.batch_alter_table(table, naming_convention=NAMING) as batch:
            name = f'fk_{table}_{column}_users'
            if restore:
                batch.create_foreign_key(name, 'users', [column], ['id'])
            else:
                batch.drop_constraint(name, type_='foreignkey')
    if connection.exec_driver_sql('PRAGMA foreign_key_check').fetchall():
        raise RuntimeError('Foreign key verification failed during workspace migration.')
    # SQLite remembers the temporary parent-table drop even after recreation.
    # Clear that deferred state only after explicit integrity verification.
    connection.exec_driver_sql('PRAGMA defer_foreign_keys=OFF')


def upgrade():
    rebuild()


def downgrade():
    connection = op.get_bind()
    for table, column in ACTORS:
        orphan = connection.execute(sa.text(
            f'SELECT 1 FROM {table} WHERE {column} NOT IN (SELECT id FROM users) LIMIT 1'
        )).first()
        if orphan:
            raise RuntimeError('Workspace records have no account. Restore the pre-upgrade backup to roll back without data loss.')
    rebuild(restore=True)
