# app/core/base.py
# Isolated SQLAlchemy Base to avoid circular imports between database, models, and domain models.

from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()
