"""Contrat de la route de santé du service IA."""

from typing import Literal

from app.models.data import StrictModel


class HealthResponse(StrictModel):
    """Décrit l'état minimal du processus HTTP."""

    status: Literal["ok"] = "ok"
    service: Literal["ai-service"] = "ai-service"


class ReadyResponse(StrictModel):
    """Décrit une session MCP initialisée et utilisable."""

    status: Literal["ready"] = "ready"
    service: Literal["ai-service"] = "ai-service"
    mcp: Literal["connected"] = "connected"


class NotReadyResponse(StrictModel):
    """Décrit l'absence de session MCP utilisable."""

    status: Literal["not_ready"] = "not_ready"
    service: Literal["ai-service"] = "ai-service"
    mcp: Literal["disconnected"] = "disconnected"
