"""Contrat de la route de santé du service IA."""

from typing import Literal

from app.models.data import StrictModel


class HealthResponse(StrictModel):
    """Décrit l'état minimal du processus HTTP."""

    status: Literal["ok"] = "ok"
    service: Literal["ai-service"] = "ai-service"
