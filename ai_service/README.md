# Service IA HBntory

Ce service expose l’API REST asynchrone utilisée par le futur client web.
Il est indépendant du Backoffice, de PostgreSQL et de l’API Produit.

## État actuel

Le service possède un client officiel MCP Streamable HTTP. Une seule session
est initialisée pendant le lifespan FastAPI, vérifie les cinq outils attendus,
puis est partagée jusqu'à sa fermeture propre à l'arrêt.

`POST /query` utilise désormais une orchestration déterministe. Un routeur de
règles reconnaît une intention explicite, effectue au maximum un appel MCP et
construit une réponse uniquement depuis les données Pydantic validées.

Aucun modèle LLM, fournisseur IA, prompt ou mécanisme de mémoire n'est encore
intégré.

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
```

La connexion Streamable HTTP est créée au démarrage du lifespan, jamais au
simple chargement d'un module. Si MCP est indisponible, `/health` reste
accessible et `/ready` retourne `503`.

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
PostgreSQL. La future classification par fournisseur IA devra conserver ces
contrats déterministes et la validation stricte actuelle.
