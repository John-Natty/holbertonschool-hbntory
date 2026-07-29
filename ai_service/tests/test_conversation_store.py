"""Tests de la mémoire conversationnelle volatile et bornée."""

import asyncio
import re

import pytest

from app.models.conversation import ConversationObservation
from app.services.conversation_store import ConversationStore


pytestmark = pytest.mark.asyncio


class FakeClock:
    """Horloge monotone contrôlée sans attente réelle."""

    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        """Avance explicitement l'horloge du test."""

        self.now += seconds


async def create_conversation(
    store: ConversationStore,
    *,
    user: str = "Où est le produit 11 ?",
    assistant: str = "Il est disponible à Carcassonne.",
) -> str:
    """Crée un échange et retourne son identifiant opaque."""

    async with store.transaction(None) as transaction:
        conversation_id = transaction.conversation_id
        transaction.record_turn(user, assistant)

    return conversation_id


async def test_store_generates_opaque_url_safe_identifier() -> None:
    """Génère un identifiant aléatoire sans donnée issue du message."""

    store = ConversationStore()

    first_id = await create_conversation(
        store,
        user="Question très personnelle à ne pas encoder",
    )
    second_id = await create_conversation(store)

    assert first_id != second_id
    assert re.fullmatch(r"[A-Za-z0-9_-]{32,64}", first_id)
    assert "personnelle" not in first_id


async def test_existing_identifier_is_reused() -> None:
    """Retourne exactement le même identifiant au tour suivant."""

    store = ConversationStore()
    conversation_id = await create_conversation(store)

    async with store.transaction(conversation_id) as transaction:
        assert transaction.conversation_id == conversation_id
        assert len(transaction.state.turns) == 1


async def test_conversations_never_share_state() -> None:
    """Isole les produits, branches et historiques de deux sessions."""

    store = ConversationStore()

    async with store.transaction(None) as first:
        first_id = first.conversation_id
        first.apply(
            ConversationObservation(
                intent="stock_by_product",
                product_id=11,
                branch_name="Toulouse",
            )
        )
        first.record_turn(
            "Où est le produit 11 ?",
            "Il est disponible à Carcassonne.",
        )

    async with store.transaction(None) as second:
        second_id = second.conversation_id
        second.apply(
            ConversationObservation(
                intent="stock_by_product",
                product_id=7,
                branch_name="Carcassonne",
            )
        )
        second.record_turn(
            "Où est le produit 7 ?",
            "Il est disponible à Toulouse.",
        )

    first_state = await store.get_state(first_id)
    second_state = await store.get_state(second_id)

    assert first_state is not None
    assert second_state is not None
    assert first_state.last_product_id == 11
    assert first_state.last_branch_name == "Toulouse"
    assert second_state.last_product_id == 7
    assert second_state.last_branch_name == "Carcassonne"
    assert first_state.turns != second_state.turns


async def test_returned_state_is_a_defensive_copy() -> None:
    """Empêche un appelant de modifier la mémoire hors transaction."""

    store = ConversationStore()
    conversation_id = await create_conversation(store)

    state = await store.get_state(conversation_id)
    assert state is not None
    state.last_product_id = 999
    state.turns.clear()

    stored_state = await store.get_state(conversation_id)

    assert stored_state is not None
    assert stored_state.last_product_id is None
    assert len(stored_state.turns) == 1


async def test_store_keeps_only_configured_number_of_turns() -> None:
    """Supprime les tours les plus anciens sans historique illimité."""

    store = ConversationStore(max_turns=2)
    conversation_id = await create_conversation(
        store,
        user="Question 1",
        assistant="Réponse 1",
    )

    for number in (2, 3, 4):
        async with store.transaction(conversation_id) as transaction:
            transaction.record_turn(
                f"Question {number}",
                f"Réponse {number}",
            )

    state = await store.get_state(conversation_id)

    assert state is not None
    assert [
        turn.user
        for turn in state.turns
    ] == [
        "Question 3",
        "Question 4",
    ]


async def test_store_redacts_secrets_and_urls_from_public_turns() -> None:
    """Ne persiste pas une clé collée par erreur dans une conversation."""

    store = ConversationStore()
    secret = "nvapi-exampleSecretValue123456"
    conversation_id = await create_conversation(
        store,
        user=(
            f"Ma clé API_KEY={secret} et le service "
            "https://internal.example/private"
        ),
        assistant=f"Authorization: Bearer {secret}",
    )

    state = await store.get_state(conversation_id)

    assert state is not None
    serialized = state.model_dump_json()
    assert secret not in serialized
    assert "internal.example" not in serialized
    assert serialized.count("donnée sensible masquée") >= 2


async def test_expired_conversation_is_removed_and_rotates_id() -> None:
    """Oublie le contexte et remplace un identifiant devenu inconnu."""

    clock = FakeClock()
    store = ConversationStore(
        ttl_seconds=10,
        clock=clock,
    )
    conversation_id = await create_conversation(store)

    clock.advance(9)
    assert await store.get_state(conversation_id) is not None

    clock.advance(11)
    await store.purge_expired()

    assert await store.get_state(conversation_id) is None
    assert await store.session_count() == 0

    async with store.transaction(conversation_id) as transaction:
        assert transaction.conversation_id != conversation_id
        assert re.fullmatch(
            r"[A-Za-z0-9_-]{32,64}",
            transaction.conversation_id,
        )
        assert transaction.state.turns == []
        assert transaction.state.last_product_id is None


async def test_session_limit_evicts_least_recently_used() -> None:
    """Borne la RAM en conservant les conversations récemment actives."""

    clock = FakeClock()
    store = ConversationStore(
        max_sessions=2,
        clock=clock,
    )
    first_id = await create_conversation(store, user="Première")
    clock.advance(1)
    second_id = await create_conversation(store, user="Deuxième")
    clock.advance(1)

    async with store.transaction(first_id):
        pass

    clock.advance(1)
    third_id = await create_conversation(store, user="Troisième")

    assert await store.session_count() == 2
    assert await store.get_state(first_id) is not None
    assert await store.get_state(second_id) is None
    assert await store.get_state(third_id) is not None


async def test_same_conversation_transactions_are_serialized() -> None:
    """Évite deux mises à jour concurrentes du même état."""

    store = ConversationStore()
    conversation_id = await create_conversation(store)
    first_entered = asyncio.Event()
    release_first = asyncio.Event()
    second_entered = asyncio.Event()

    async def first_request() -> None:
        async with store.transaction(conversation_id):
            first_entered.set()
            await release_first.wait()

    async def second_request() -> None:
        await first_entered.wait()
        async with store.transaction(conversation_id):
            second_entered.set()

    first_task = asyncio.create_task(first_request())
    second_task = asyncio.create_task(second_request())

    await first_entered.wait()
    await asyncio.sleep(0.01)
    assert not second_entered.is_set()

    release_first.set()
    await asyncio.gather(first_task, second_task)

    assert second_entered.is_set()


async def test_different_conversations_do_not_share_one_lock() -> None:
    """Permet à deux sessions indépendantes de progresser en parallèle."""

    store = ConversationStore()
    first_id = await create_conversation(store, user="Première")
    second_id = await create_conversation(store, user="Deuxième")
    first_entered = asyncio.Event()
    release_first = asyncio.Event()
    second_entered = asyncio.Event()

    async def hold_first() -> None:
        async with store.transaction(first_id):
            first_entered.set()
            await release_first.wait()

    async def enter_second() -> None:
        await first_entered.wait()
        async with store.transaction(second_id):
            second_entered.set()

    first_task = asyncio.create_task(hold_first())
    second_task = asyncio.create_task(enter_second())

    await asyncio.wait_for(second_entered.wait(), timeout=0.5)
    assert not first_task.done()

    release_first.set()
    await asyncio.gather(first_task, second_task)
