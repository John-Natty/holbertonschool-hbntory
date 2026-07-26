# Service IA HBntory

Ce service expose l’API REST asynchrone utilisée par le futur client web.
Il est indépendant du Backoffice, de PostgreSQL et de l’API Produit.

## État actuel

Le service possède un client officiel MCP Streamable HTTP. Une seule session
est initialisée pendant le lifespan FastAPI, vérifie les cinq outils attendus,
puis est partagée jusqu'à sa fermeture propre à l'arrêt.

`POST /query` utilise une orchestration déterministe. Le mode par défaut
applique uniquement les règles locales. Un mode Ollama optionnel peut proposer
une intention structurée comme seconde chance lorsqu'elles ne comprennent pas
la question.

Ollama ne génère jamais la réponse métier et ne possède aucun mécanisme de
tool calling. Sa sortie est validée par les modèles Pydantic existants puis
par une vérification d'ancrage dans la question. L'orchestrateur conserve seul
le choix parmi les cinq méthodes MCP et construit la réponse finale depuis les
données MCP validées.

Routes disponibles :

- `GET /health` : état du processus HTTP ;
- `GET /ready` : disponibilité de la session MCP, avec `200` ou `503` ;
- `POST /query` : validation et traitement injectable d'une question.

## Questions reconnues

Le routeur accepte six intentions :

- `product_list` : `liste les produits`, `liste les 10 premiers produits`
  ou `affiche les produits à partir de 20` ;
- `product_details` : `détails du produit 12`, `montre le produit 12` ou
  `quel est le prix du produit 12` ;
- `stock_by_product` : `où trouver le produit 12` ou
  `stock du produit 12` ;
- `stock_by_branch` : `stock de la branche 3` ou
  `que contient la branche 3` ;
- `shopping_list` : liste explicite d'identifiants et de quantités ;
- `unsupported` : demande inconnue, incomplète ou contradictoire.

Le format fermé d'une liste d'achats est par exemple :

```text
liste d'achats : produit 12 x2, produit 7 x1
vérifie la liste : 12 x2, 7 x1
où acheter 12 x2 et 7 x1
```

Les identifiants et quantités doivent être des entiers strictement positifs.
Les doublons sont transmis sans transformation silencieuse. Un nom de produit
n'est jamais converti en identifiant.

Une question incomplète, telle que `stock de la branche`, ou une demande
contenant plusieurs actions retourne une clarification de type `text` sans
appel MCP.

## Codes HTTP de POST /query

- `200` : résultat MCP validé ou clarification sans donnée métier ;
- `404` : produit ou branche absent ;
- `422` : paramètres MCP invalides ;
- `502` : réponse MCP invalide ou autre erreur métier contrôlée ;
- `503` : serveur MCP indisponible ;
- `504` : délai MCP dépassé ;
- `500` : bug inattendu, avec un corps générique sans détail interne.

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
MCP_REQUEST_TIMEOUT_SECONDS=10
MCP_MAX_CONCURRENT_CALLS=10
AI_INTENT_PROVIDER=rules
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODEL=gemma3:latest
OLLAMA_REQUEST_TIMEOUT_SECONDS=30
```

La connexion Streamable HTTP est créée au démarrage du lifespan, jamais au
simple chargement d'un module. Si MCP est indisponible, `/health` reste
accessible et `/ready` retourne `503`.

`AI_INTENT_PROVIDER` accepte :

- `rules` : aucune création de client Ollama et aucun appel réseau ;
- `ollama` : règles prioritaires, puis une classification Ollama maximum
  uniquement pour une intention `unsupported`.

Le client HTTP Ollama est partagé pendant tout le lifespan et fermé à l'arrêt.
Une panne, un timeout ou une sortie invalide conserve la clarification
déterministe avec un statut `200`. Ollama n'est pas pris en compte par
`/ready`.

Pour vérifier manuellement que le modèle configuré existe déjà localement :

```bash
ollama show gemma3:latest
```

Cette commande ne télécharge aucun modèle. L'intégration d'Ollama à Docker
Compose sera réalisée dans une phase ultérieure.

## Lancement local

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m app.main
```

## Tests

Les tests utilisent directement l'application ASGI et des doubles injectés
autour du transport, de la session et du client MCP, sans serveur ni réseau :

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  -m pytest -v -p no:cacheprovider
```

L'orchestration n'appelle jamais directement le Backoffice, l'API Produit ou
PostgreSQL. Le classificateur ne reçoit ni données MCP, ni stock, ni produit,
ni URL métier, et ses textes ne sont jamais utilisés comme réponse publique.
