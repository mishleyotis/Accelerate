"""SQLAlchemy Core table definitions.

The DMA Insights backend serves every surface with hand-written
``sqlalchemy.text()`` SQL and hand-written Alembic migrations
(``target_metadata = None`` — no autogenerate). This package therefore
holds SQLAlchemy Core ``Table`` objects purely as the declarative schema
artifact for a table — a typed, in-code description of the columns the
raw-SQL endpoints read/write — NOT an ORM mapping and NOT the migration
source of truth (the migration is).
"""
