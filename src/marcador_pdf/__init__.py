"""Marcações de revisão em PDF no padrão do Adobe Acrobat, gravadas por código."""
from .conferir import conferir
from .marcar import Marcador
from .reparar import reparar

__all__ = ["Marcador", "conferir", "reparar"]
__version__ = "0.1.0"
