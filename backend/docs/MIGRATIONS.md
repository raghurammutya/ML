# Database Migrations with Alembic

## Overview

This project uses [Alembic](https://alembic.sqlalchemy.org/) for database schema migrations, enabling zero-downtime deployments and version-controlled database changes.

## Quick Start

### Check Current Migration State
```bash
alembic current
```

### Create a New Migration
```bash
# Auto-generate migration from model changes
alembic revision --autogenerate -m "description of changes"

# Or create empty migration template
alembic revision -m "description of changes"
```

### Apply Migrations
```bash
# Upgrade to latest version
alembic upgrade head

# Upgrade to specific version
alembic upgrade b80c16c4db24

# Upgrade one version forward
alembic upgrade +1
```

### Rollback Migrations
```bash
# Downgrade one version
alembic downgrade -1

# Downgrade to specific version
alembic downgrade b80c16c4db24

# Downgrade to base (WARNING: removes all tables)
alembic downgrade base
```

### View Migration History
```bash
# Show all migrations
alembic history

# Show current migration with details
alembic current --verbose
```

## Migration Workflow

### Development
1. **Make schema changes** to your models or write SQL
2. **Generate migration**:
   ```bash
   alembic revision -m "add user_preferences table"
   ```
3. **Edit migration file** in `alembic/versions/`
4. **Test migration**:
   ```bash
   alembic upgrade head  # Apply
   alembic downgrade -1  # Test rollback
   alembic upgrade head  # Re-apply
   ```
5. **Commit migration** to git

### Staging/Production
1. **Pull latest code** with migrations
2. **Review pending migrations**:
   ```bash
   alembic history
   ```
3. **Apply migrations**:
   ```bash
   alembic upgrade head
   ```
4. **Verify success**:
   ```bash
   alembic current
   ```

## Zero-Downtime Migrations

### Safe Migration Patterns

#### Adding a Column (Safe)
```python
def upgrade():
    op.add_column('users', sa.Column('email', sa.String(255), nullable=True))
    # Set default values if needed
    op.execute("UPDATE users SET email = username || '@example.com' WHERE email IS NULL")
    # Make NOT NULL after populating
    op.alter_column('users', 'email', nullable=False)

def downgrade():
    op.drop_column('users', 'email')
```

#### Renaming a Column (Requires Multiple Steps)
**Migration 1**: Add new column
```python
def upgrade():
    op.add_column('users', sa.Column('full_name', sa.String(255)))
    # Copy data
    op.execute("UPDATE users SET full_name = first_name")
```

**Migration 2** (after code deploy): Remove old column
```python
def upgrade():
    op.drop_column('users', 'first_name')
```

#### Adding an Index (Safe)
```python
def upgrade():
    # Use CONCURRENTLY to avoid locking (requires raw SQL for PostgreSQL)
    op.execute("CREATE INDEX CONCURRENTLY idx_users_email ON users(email)")

def downgrade():
    op.drop_index('idx_users_email', table_name='users')
```

### Unsafe Patterns (Avoid in Production)
❌ Dropping columns immediately
❌ Renaming tables without multi-step process
❌ Changing column types without data migration
❌ Adding NOT NULL constraints without defaults

## Migration File Structure

```python
"""brief description of migration

Detailed description if needed.

Revision ID: abc123def456
Revises: xyz789
Create Date: 2025-11-09 08:43:07

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic
revision = 'abc123def456'
down_revision = 'xyz789'  # Previous migration
branch_labels = None
depends_on = None


def upgrade():
    """Apply schema changes"""
    # Add your migration logic here
    op.create_table(
        'user_preferences',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('user_id', sa.String(100), nullable=False),
        sa.Column('theme', sa.String(20), default='light'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('idx_user_prefs_user_id', 'user_preferences', ['user_id'])


def downgrade():
    """Rollback schema changes"""
    op.drop_index('idx_user_prefs_user_id')
    op.drop_table('user_preferences')
```

## TimescaleDB Considerations

For TimescaleDB hypertables:

```python
def upgrade():
    # Create regular table first
    op.create_table(
        'metrics',
        sa.Column('time', sa.DateTime(timezone=True), primary_key=True),
        sa.Column('value', sa.Float()),
    )

    # Convert to hypertable (raw SQL required)
    op.execute("""
        SELECT create_hypertable(
            'metrics',
            'time',
            if_not_exists => TRUE
        )
    """)

def downgrade():
    # Drop hypertable (regular DROP TABLE works)
    op.drop_table('metrics')
```

## Troubleshooting

### "Target database is not up to date"
```bash
# Check current version
alembic current

# Check migration history
alembic history

# Force stamp to specific version (CAREFUL!)
alembic stamp head
```

### "Multiple heads detected"
This happens when multiple migrations have the same parent. Merge them:
```bash
alembic merge -m "merge multiple heads" head1 head2
```

### "Can't locate revision identified by 'xyz'"
Migration file is missing. Either:
1. Pull missing migration from git
2. Or remove reference from database:
```sql
DELETE FROM alembic_version WHERE version_num = 'xyz';
```

### Environment Variables Not Loading
Alembic uses `alembic/env.py` which loads from `app/config.py`. Ensure `.env` file exists:
```bash
cp .env.template .env
# Edit .env with correct values
```

## Configuration

### alembic.ini
Main configuration file. Database URL is set programmatically in `env.py`.

### alembic/env.py
Environment configuration that:
- Loads app settings from `app/config.py`
- Constructs database URL
- Handles async migrations with asyncpg
- Supports both online and offline modes

## Best Practices

### ✅ DO
- Write both `upgrade()` and `downgrade()` functions
- Test migrations locally before deploying
- Use descriptive migration messages
- Keep migrations small and focused
- Add comments for complex logic
- Test rollbacks before deploying
- Use transactions for data migrations

### ❌ DON'T
- Modify existing migration files after they're deployed
- Skip migration testing
- Mix schema and data changes in one migration (split them)
- Use `downgrade base` in production
- Deploy code before running migrations
- Forget to handle NULL values when adding NOT NULL columns

## Migration Checklist

Before deploying a migration to production:

- [ ] Migration has both upgrade and downgrade functions
- [ ] Tested upgrade locally
- [ ] Tested downgrade locally
- [ ] Tested upgrade again after downgrade
- [ ] No data loss in upgrade/downgrade cycle
- [ ] Migration is idempotent (can run multiple times safely)
- [ ] Large data migrations use batching
- [ ] Reviewed SQL statements for performance impact
- [ ] Indexes created with CONCURRENTLY if needed
- [ ] Rollback plan documented
- [ ] Monitoring/alerts configured for migration

## CI/CD Integration

### GitHub Actions Example
```yaml
- name: Run database migrations
  run: |
    alembic upgrade head
  env:
    DB_PASSWORD: ${{ secrets.DB_PASSWORD }}
    ENVIRONMENT: production
```

### Pre-deployment Check
```bash
# In CI pipeline
alembic check  # Verify migrations can run
alembic history  # Show pending migrations
```

## Baseline Migration

The initial migration `b80c16c4db24_baseline_existing_database_schema.py` represents the database state as of 2025-11-09. It's a no-op migration that marks the starting point for Alembic-managed migrations.

All previous manual SQL migrations (001-029) are considered already applied.

## Further Reading

- [Alembic Tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html)
- [Alembic Operations Reference](https://alembic.sqlalchemy.org/en/latest/ops.html)
- [PostgreSQL ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html)
- [TimescaleDB Hypertables](https://docs.timescale.com/use-timescale/latest/hypertables/)
