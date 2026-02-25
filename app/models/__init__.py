from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all SQLAlchemy models."""


# Re-export all models so Alembic autogenerate detects them.
# These imports MUST come after `Base` is defined to avoid circular imports.
from .business_rule import BusinessRule as BusinessRule  # noqa: E402
from .graph import GraphEdge as GraphEdge  # noqa: E402
from .graph import GraphNode as GraphNode  # noqa: E402
from .knowledge import KnowledgeDocument as KnowledgeDocument  # noqa: E402
from .plan import Plan as Plan  # noqa: E402
from .project import Project as Project  # noqa: E402

__all__ = [
    "Base",
    "Project",
    "Plan",
    "BusinessRule",
    "KnowledgeDocument",
    "GraphNode",
    "GraphEdge",
]
