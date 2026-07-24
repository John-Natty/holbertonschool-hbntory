# Service IA HBntory

Ce service expose l’API REST asynchrone utilisée par le futur client web.
Il est indépendant du Backoffice, de PostgreSQL et de l’API Produit.

## État actuel

Cette première phase fournit les contrats REST, la validation Pydantic et
l’injection du service de requête. Le client MCP et le modèle IA ne sont pas
encore connectés. Par conséquent, `POST /query` retourne temporairement une
erreur structurée `503 service_unavailable`.

Routes disponibles :

- `GET /health` : état du processus HTTP ;
- `POST /query` : validation et traitement injectable d’une question.

## Installation

```bash
cd ai_service

uv venv .venv --python 3.12

uv pip install \
  --python .venv/bin/python \
  -r requirements.txt \
  -r requirements-dev.txt
```

## Configuration

Valeurs par défaut :

```text
AI_SERVICE_HOST=0.0.0.0
AI_SERVICE_PORT=8001
MCP_SERVER_URL=http://product-mcp-server:8000/mcp
```

Ces paramètres n’établissent aucune connexion réseau au chargement.

## Lancement local

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m app.main
```

## Tests

Les tests utilisent directement l’application ASGI sans serveur ni réseau :

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  -m pytest -v -p no:cacheprovider
```

Le client MCP Streamable HTTP et le fournisseur IA seront ajoutés lors des
phases suivantes.
