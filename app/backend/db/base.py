"""
Clase Base declarativa para todos los modelos SQLAlchemy.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """
    Clase base para todos los modelos ORM.
    Hereda de DeclarativeBase (SQLAlchemy 2.0).
    """
    
    pass
