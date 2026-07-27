"""Abstraction locale des fournisseurs de classification."""

from typing import Protocol

from app.models.intents import QueryIntent


class IntentClassifier(Protocol):
    """Contrat d'un classificateur retournant une intention stricte."""

    async def classify(
        self,
        question: str,
    ) -> QueryIntent:
        """Classe une question sans produire de réponse métier."""

        ...
