"""
Interfaz base para todos los proveedores de IA.
Historia en formato común: list[{"role": "user"|"assistant", "content": str}]
"""
from abc import ABC, abstractmethod


class BaseProvider(ABC):

    @abstractmethod
    async def generate(
        self,
        system_prompt: str,
        history: list[dict],   # [{"role": "user"|"assistant", "content": "..."}]
        message: str,
    ) -> str:
        """Genera una respuesta dado el system prompt, historial y mensaje nuevo."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Nombre del proveedor (para logs)."""
        ...
