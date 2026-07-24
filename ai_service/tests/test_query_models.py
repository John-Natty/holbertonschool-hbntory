"""Tests des contrats Pydantic publics du service IA."""

from copy import deepcopy

import pytest
from pydantic import TypeAdapter, ValidationError

from app.models.query import (
    ErrorResponse,
    ProductDetailsResponse,
    ProductListResponse,
    QueryRequest,
    QueryResponse,
    ShoppingListResponse,
    StockByBranchResponse,
    StockByProductResponse,
    TextResponse,
)


QUERY_RESPONSE_ADAPTER = TypeAdapter(QueryResponse)


def sample_supplier() -> dict:
    """Retourne un fournisseur local valide."""

    return {
        "id": "SUP-TEST-001",
        "name": "Fournisseur de test",
        "contact_email": "supplier@example.test",
        "country": "France",
        "lead_time_days": 2,
        "reliability_score": 0.99,
    }


def sample_product() -> dict:
    """Retourne un produit local valide."""

    return {
        "id": 12,
        "sku": "HB-TEST-0012",
        "name": "Produit de test",
        "description": "Description du produit.",
        "category": "Tests",
        "brand": "HBntory",
        "supplier_id": "SUP-TEST-001",
        "supplier_name": "Fournisseur de test",
        "unit_price": 49.99,
        "currency": "EUR",
        "discontinued": False,
        "weight_kg": 1.25,
        "tags": ["test", "ia"],
        "updated_at": "2026-07-24T12:00:00Z",
        "supplier": sample_supplier(),
    }


def valid_response_payloads() -> dict[str, dict]:
    """Retourne une réponse valide pour chaque type public."""

    product = sample_product()

    return {
        "product_list": {
            "success": True,
            "answer": "Un produit est disponible.",
            "type": "product_list",
            "data": {
                "count": 1,
                "limit": 20,
                "offset": 0,
                "products": [product],
            },
            "error": None,
        },
        "product_details": {
            "success": True,
            "answer": "Voici le produit demandé.",
            "type": "product_details",
            "data": {
                "product": product,
            },
            "error": None,
        },
        "stock_by_product": {
            "success": True,
            "answer": "Le produit est disponible à Toulouse.",
            "type": "stock_by_product",
            "data": {
                "product_id": 12,
                "branches": [
                    {
                        "branch_id": 1,
                        "branch_name": "Toulouse",
                        "quantity": 8,
                    },
                ],
            },
            "error": None,
        },
        "stock_by_branch": {
            "success": True,
            "answer": "La branche possède un produit.",
            "type": "stock_by_branch",
            "data": {
                "branch": {
                    "id": 1,
                    "name": "Toulouse",
                },
                "stocks": [
                    {
                        "product_id": 12,
                        "quantity": 8,
                    },
                ],
            },
            "error": None,
        },
        "shopping_list": {
            "success": True,
            "answer": "Toulouse satisfait la liste.",
            "type": "shopping_list",
            "data": {
                "matching_branches": [
                    {
                        "branch_id": 1,
                        "branch_name": "Toulouse",
                        "items": [
                            {
                                "product_id": 12,
                                "requested_quantity": 2,
                                "available_quantity": 8,
                            },
                        ],
                    },
                ],
            },
            "error": None,
        },
        "text": {
            "success": True,
            "answer": "Précisez le produit recherché.",
            "type": "text",
            "data": None,
            "error": None,
        },
        "error": {
            "success": False,
            "answer": "Le service de données est indisponible.",
            "type": "error",
            "data": None,
            "error": {
                "code": "service_unavailable",
                "message": "Le serveur MCP est indisponible.",
            },
        },
    }


RESPONSE_CLASSES = {
    "product_list": ProductListResponse,
    "product_details": ProductDetailsResponse,
    "stock_by_product": StockByProductResponse,
    "stock_by_branch": StockByBranchResponse,
    "shopping_list": ShoppingListResponse,
    "text": TextResponse,
    "error": ErrorResponse,
}


def test_query_request_strips_surrounding_spaces():
    """Nettoie les espaces autour d'une question valide."""

    request = QueryRequest(
        question="  Où trouver le produit 12 ?  "
    )

    assert request.question == "Où trouver le produit 12 ?"


def test_query_request_accepts_maximum_length():
    """Accepte exactement deux mille caractères."""

    request = QueryRequest(question="a" * 2000)

    assert len(request.question) == 2000


@pytest.mark.parametrize(
    "invalid_question",
    [
        pytest.param("", id="empty"),
        pytest.param("   ", id="whitespace"),
        pytest.param("a" * 2001, id="too-long"),
        pytest.param(12, id="number"),
        pytest.param(True, id="boolean"),
        pytest.param(
            {
                "text": "question",
            },
            id="object",
        ),
    ],
)
def test_query_request_rejects_invalid_question(
    invalid_question,
):
    """Refuse les questions vides, longues ou non textuelles."""

    with pytest.raises(ValidationError):
        QueryRequest(question=invalid_question)


def test_query_request_rejects_extra_field():
    """Refuse les champs publics supplémentaires."""

    with pytest.raises(ValidationError):
        QueryRequest(
            question="Question valide",
            unexpected=True,
        )


@pytest.mark.parametrize(
    "response_type",
    list(RESPONSE_CLASSES),
)
def test_query_response_accepts_each_variant(response_type):
    """Valide les sept variantes discriminées du contrat public."""

    payload = valid_response_payloads()[response_type]
    response = QUERY_RESPONSE_ADAPTER.validate_python(payload)

    assert isinstance(
        response,
        RESPONSE_CLASSES[response_type],
    )
    assert set(response.model_dump(mode="json")) == {
        "success",
        "answer",
        "type",
        "data",
        "error",
    }


def invalid_consistency_payloads() -> list:
    """Construit les incohérences interdites du contrat public."""

    payloads = valid_response_payloads()

    success_with_error = deepcopy(payloads["product_list"])
    success_with_error["error"] = {
        "code": "client_error",
        "message": "Erreur interdite.",
    }

    error_with_data = deepcopy(payloads["error"])
    error_with_data["data"] = {
        "unexpected": True,
    }

    failed_success_type = deepcopy(payloads["product_list"])
    failed_success_type["success"] = False

    successful_error_type = deepcopy(payloads["error"])
    successful_error_type["success"] = True

    extra_field = deepcopy(payloads["text"])
    extra_field["unexpected"] = True

    empty_answer = deepcopy(payloads["text"])
    empty_answer["answer"] = "   "

    return [
        success_with_error,
        error_with_data,
        failed_success_type,
        successful_error_type,
        extra_field,
        empty_answer,
    ]


@pytest.mark.parametrize(
    "payload",
    invalid_consistency_payloads(),
)
def test_query_response_rejects_inconsistencies(payload):
    """Refuse les combinaisons success, type, data et error invalides."""

    with pytest.raises(ValidationError):
        QUERY_RESPONSE_ADAPTER.validate_python(payload)


def invalid_business_payloads() -> list:
    """Construit des données métier volontairement invalides."""

    payloads = valid_response_payloads()

    zero_product_id = deepcopy(payloads["product_details"])
    zero_product_id["data"]["product"]["id"] = 0

    zero_branch_id = deepcopy(payloads["stock_by_product"])
    zero_branch_id["data"]["branches"][0]["branch_id"] = 0

    negative_quantity = deepcopy(payloads["stock_by_branch"])
    negative_quantity["data"]["stocks"][0]["quantity"] = -1

    non_finite_price = deepcopy(payloads["product_details"])
    non_finite_price["data"]["product"]["unit_price"] = float(
        "nan"
    )

    non_finite_score = deepcopy(payloads["product_details"])
    non_finite_score["data"]["product"]["supplier"][
        "reliability_score"
    ] = float("inf")

    numeric_identifier_string = deepcopy(
        payloads["stock_by_product"]
    )
    numeric_identifier_string["data"]["product_id"] = "12"

    extra_business_field = deepcopy(payloads["stock_by_branch"])
    extra_business_field["data"]["branch"]["unexpected"] = True

    return [
        zero_product_id,
        zero_branch_id,
        negative_quantity,
        non_finite_price,
        non_finite_score,
        numeric_identifier_string,
        extra_business_field,
    ]


@pytest.mark.parametrize(
    "payload",
    invalid_business_payloads(),
)
def test_query_response_rejects_invalid_business_data(payload):
    """Refuse les données métier faibles, non finies ou inattendues."""

    with pytest.raises(ValidationError):
        QUERY_RESPONSE_ADAPTER.validate_python(payload)
