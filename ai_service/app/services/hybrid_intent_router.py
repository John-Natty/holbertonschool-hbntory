"""Routeur donnant la priorité aux règles puis au classificateur."""

from app.errors import IntentClassifierError
from app.models.intents import QueryIntent, UnsupportedIntent
from app.services.intent_anchor import IntentAnchorValidator
from app.services.intent_classifier import IntentClassifier
from app.services.intent_router import IntentRouter


class HybridIntentRouter:
    """Utilise le fournisseur une seule fois après un échec des règles."""

    def __init__(
        self,
        rule_router: IntentRouter,
        classifier: IntentClassifier | None,
        anchor_validator: IntentAnchorValidator,
    ) -> None:
        """Injecte les règles, le fournisseur optionnel et l'ancrage."""

        self._rule_router = rule_router
        self._classifier = classifier
        self._anchor_validator = anchor_validator

    async def resolve(
        self,
        question: str,
    ) -> QueryIntent:
        """Retourne une intention sûre ou le fallback déterministe."""

        deterministic_intent = await self._rule_router.resolve(
            question
        )

        if not isinstance(
            deterministic_intent,
            UnsupportedIntent,
        ):
            return deterministic_intent

        if self._classifier is None:
            return deterministic_intent

        try:
            classified_intent = await self._classifier.classify(
                question
            )
        except IntentClassifierError:
            return deterministic_intent

        if isinstance(classified_intent, UnsupportedIntent):
            return deterministic_intent

        if not self._anchor_validator.is_anchored(
            question,
            classified_intent,
        ):
            return deterministic_intent

        return classified_intent
