# Database migrations

`versions/0001_initial.py` is the v0 bootstrap migration and uses the immutable model snapshot shipped with v0.1.0 to create/drop the schema. `0001_initial_postgresql.sql` is a rendered PostgreSQL DDL snapshot for review and deployment systems that prefer SQL artifacts.

For subsequent revisions, use explicit Alembic `op.*` migrations rather than editing the bootstrap revision or silently changing historical DDL.
