"""Mémoire conversationnelle RAM bornée et sûre en concurrence."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from contextlib import asynccontextmanager
from dataclasses import dataclass
from time import monotonic
from typing import AsyncIterator, Callable

from app.models.conversation import (
    ConversationId,
    ConversationObservation,
    ConversationState,
    ConversationTurn,
    generate_conversation_id,
    redact_sensitive_text,
    validate_conversation_id,
)


DEFAULT_CONVERSATION_TTL_SECONDS = 1800
DEFAULT_CONVERSATION_MAX_TURNS = 10
DEFAULT_CONVERSATION_MAX_SESSIONS = 1000
MAX_STORED_USER_CHARACTERS = 2000
MAX_STORED_ASSISTANT_CHARACTERS = 8000


class ConversationCapacityError(RuntimeError):
    """Signale que toutes les sessions bornées sont actuellement actives."""


@dataclass(slots=True)
class _Session:
    """État interne jamais exposé directement aux consommateurs."""

    state: ConversationState
    updated_at: float
    lock: asyncio.Lock
    in_use: int = 0


class ConversationTransaction:
    """Copie isolée d'une conversation, validée avant son commit."""

    def __init__(
        self,
        conversation_id: ConversationId,
        state: ConversationState,
        max_turns: int,
    ) -> None:
        """Prépare une copie modifiable sans toucher à l'état partagé."""

        self.conversation_id = conversation_id
        self.state = state
        self._max_turns = max_turns

    def apply(self, observation: ConversationObservation) -> None:
        """Applique un résultat métier préalablement réduit."""

        self.state.apply(observation)

    def record_turn(self, user: str, assistant: str) -> None:
        """Ajoute un échange public puis tronque l'historique ancien."""

        turn = ConversationTurn(
            user=redact_sensitive_text(
                user,
                MAX_STORED_USER_CHARACTERS,
            ),
            assistant=redact_sensitive_text(
                assistant,
                MAX_STORED_ASSISTANT_CHARACTERS,
            ),
        )
        self.state.turns.append(turn)
        self.state.turns = self.state.turns[-self._max_turns :]


class ConversationStore:
    """Stocke un LRU borné avec un verrou distinct par conversation."""

    def __init__(
        self,
        ttl_seconds: float = DEFAULT_CONVERSATION_TTL_SECONDS,
        max_turns: int = DEFAULT_CONVERSATION_MAX_TURNS,
        max_sessions: int = DEFAULT_CONVERSATION_MAX_SESSIONS,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        """Valide les bornes et initialise le registre vide."""

        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds doit être strictement positif.")
        if not 1 <= max_turns <= 50:
            raise ValueError("max_turns doit être compris entre 1 et 50.")
        if max_sessions <= 0:
            raise ValueError("max_sessions doit être strictement positif.")

        self._ttl_seconds = ttl_seconds
        self._max_turns = max_turns
        self._max_sessions = max_sessions
        self._clock = clock
        self._sessions: OrderedDict[str, _Session] = OrderedDict()
        self._registry_lock = asyncio.Lock()

    @asynccontextmanager
    async def transaction(
        self,
        conversation_id: str | None = None,
    ) -> AsyncIterator[ConversationTransaction]:
        """Sérialise un tour et commit sa copie seulement sans exception."""

        identifier, session = await self._reserve(conversation_id)

        try:
            await session.lock.acquire()
        except BaseException:
            await self._release_reservation(identifier, session)
            raise

        transaction = ConversationTransaction(
            conversation_id=identifier,
            state=session.state.model_copy(deep=True),
            max_turns=self._max_turns,
        )

        try:
            yield transaction
        except BaseException:
            raise
        else:
            validated_state = ConversationState.model_validate(
                transaction.state.model_dump(mode="python")
            )

            async with self._registry_lock:
                current = self._sessions.get(identifier)

                if current is not session:
                    raise RuntimeError(
                        "La session réservée a disparu avant son commit."
                    )

                session.state = validated_state
                session.updated_at = self._clock()
                self._sessions.move_to_end(identifier)
        finally:
            session.lock.release()
            await self._release_reservation(identifier, session)

    async def get_state(
        self,
        conversation_id: str,
    ) -> ConversationState | None:
        """Retourne une copie de diagnostic ou ``None`` après expiration."""

        identifier = validate_conversation_id(conversation_id)

        async with self._registry_lock:
            now = self._clock()
            self._purge_expired_locked(now)
            session = self._sessions.get(identifier)

            if session is None:
                return None

            self._sessions.move_to_end(identifier)
            return session.state.model_copy(deep=True)

    async def purge_expired(self) -> int:
        """Supprime les conversations inactives qui ne sont pas utilisées."""

        async with self._registry_lock:
            return self._purge_expired_locked(self._clock())

    async def session_count(self) -> int:
        """Retourne le nombre de sessions présentes après nettoyage."""

        async with self._registry_lock:
            self._purge_expired_locked(self._clock())
            return len(self._sessions)

    async def clear(self) -> None:
        """Efface la mémoire volatile lors de l'arrêt du processus."""

        async with self._registry_lock:
            self._sessions.clear()

    async def _reserve(
        self,
        conversation_id: str | None,
    ) -> tuple[ConversationId, _Session]:
        """Réserve une session contre l'expiration et l'éviction LRU."""

        requested_identifier = (
            generate_conversation_id()
            if conversation_id is None
            else validate_conversation_id(conversation_id)
        )

        async with self._registry_lock:
            now = self._clock()
            self._purge_expired_locked(now)
            session = self._sessions.get(requested_identifier)

            if session is None:
                self._make_room_locked()
                identifier = self._new_identifier_locked()
                session = _Session(
                    state=ConversationState(),
                    updated_at=now,
                    lock=asyncio.Lock(),
                )
                self._sessions[identifier] = session
            else:
                identifier = requested_identifier

            session.in_use += 1
            session.updated_at = now
            self._sessions.move_to_end(identifier)
            return identifier, session

    def _new_identifier_locked(self) -> ConversationId:
        """Génère un identifiant absent du registre courant."""

        for _attempt in range(10):
            identifier = generate_conversation_id()

            if identifier not in self._sessions:
                return identifier

        raise RuntimeError(
            "Impossible de générer un identifiant de conversation unique."
        )

    async def _release_reservation(
        self,
        identifier: str,
        session: _Session,
    ) -> None:
        """Libère la protection anti-éviction d'une transaction."""

        async with self._registry_lock:
            current = self._sessions.get(identifier)

            if current is not session:
                return

            session.in_use -= 1

            if session.in_use < 0:
                raise RuntimeError(
                    "Compteur d'utilisation conversationnel incohérent."
                )

    def _purge_expired_locked(self, now: float) -> int:
        """Nettoie les entrées expirées sous le verrou du registre."""

        expired = [
            identifier
            for identifier, session in self._sessions.items()
            if (
                session.in_use == 0
                and now - session.updated_at >= self._ttl_seconds
            )
        ]

        for identifier in expired:
            del self._sessions[identifier]

        return len(expired)

    def _make_room_locked(self) -> None:
        """Évince la session inactive la moins récemment utilisée."""

        if len(self._sessions) < self._max_sessions:
            return

        for identifier, session in self._sessions.items():
            if session.in_use == 0:
                del self._sessions[identifier]
                return

        raise ConversationCapacityError(
            "Toutes les conversations disponibles sont actives."
        )
