# Service IA HBntory

Ce service expose l’API REST asynchrone utilisée par le futur client web.
Il est indépendant du Backoffice, de PostgreSQL et de l’API Produit.

## État actuel

Le service possède un client officiel MCP Streamable HTTP. Une seule session
active est partagée pendant le lifespan FastAPI et vérifie les cinq outils
attendus. Si elle est perdue, elle est fermée puis remplacée par une
reconnexion bornée et synchronisée.

`POST /api/query` utilise une orchestration déterministe. Le mode par défaut
applique uniquement les règles locales. Un mode Ollama optionnel peut proposer
une intention structurée comme seconde chance lorsqu'elles ne comprennent pas
la question.

Ollama ne génère jamais la réponse métier et ne possède aucun mécanisme de
tool calling. Sa sortie est validée par les modèles Pydantic existants puis
par une vérification d'ancrage dans la question. L'orchestrateur conserve seul
le choix parmi les cinq méthodes MCP et construit la réponse finale depuis les
données MCP validées. Une requête publique exécute au maximum un appel MCP
métier.

Les réponses de stock par branche citent directement chaque `product_id` et sa
quantité à partir de la réponse MCP déjà validée. Les listes d'achats nomment
toutes les branches satisfaisantes. Cette mise en forme ne déclenche jamais de
second appel MCP et n'invente aucun nom de produit.

Routes disponibles :

- `GET /health` : état du processus HTTP ;
- `GET /ready` : disponibilité de la session MCP, avec `200` ou `503` ;
- `POST /api/query` : validation et traitement injectable d'une question.

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

## Codes HTTP de POST /api/query

- `200` : résultat MCP validé ou clarification sans donnée métier ;
- `404` : produit ou branche absent ;
- `422` : requête ou paramètres invalides, avec un `ErrorResponse` stable ;
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
CORS_ALLOWED_ORIGINS=http://localhost:8080
MCP_SERVER_URL=http://product-mcp-server:8000/mcp
MCP_REQUEST_TIMEOUT_SECONDS=10
MCP_MAX_CONCURRENT_CALLS=10
MCP_RECONNECT_ATTEMPTS=3
MCP_RECONNECT_INITIAL_DELAY_SECONDS=0.25
MCP_RECONNECT_MAX_DELAY_SECONDS=2
AI_INTENT_PROVIDER=rules
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODEL=gemma3:latest
OLLAMA_REQUEST_TIMEOUT_SECONDS=30
```

`CORS_ALLOWED_ORIGINS` contient une ou plusieurs origines HTTP explicites,
séparées par des virgules. Les espaces sont supprimés et une liste vide est
refusée. Par défaut, seul le client web de développement servi depuis
`http://localhost:8080` est autorisé. La politique accepte `GET`, `POST` et
`OPTIONS`, ainsi que l'en-tête `Content-Type`, sans credentials navigateur.

La connexion Streamable HTTP est créée au démarrage du lifespan, jamais au
simple chargement d'un module. Si MCP est indisponible, `/health` reste
accessible, `/ready` retourne `503` et `/api/query` retourne une erreur
structurée `503`. Le processus FastAPI reste démarré.

Lorsqu'une session est absente, `/ready` et `/api/query` peuvent déclencher une
reconnexion protégée par un verrou. Trois tentatives sont effectuées par
défaut avec un backoff initial de 0,25 seconde, plafonné à 2 secondes. Une
seule session est créée même si plusieurs requêtes demandent simultanément
une récupération. Après le retour du MCP, aucune relance manuelle du service
IA n'est nécessaire.

`AI_INTENT_PROVIDER` accepte :

- `rules` : aucune création de client Ollama et aucun appel réseau ;
- `ollama` : règles prioritaires, puis une classification Ollama maximum
  uniquement pour une intention `unsupported`.

Le client HTTP Ollama est partagé pendant tout le lifespan et fermé à l'arrêt.
Une panne, un timeout ou une sortie invalide conserve la clarification
déterministe avec un statut `200`. Ollama n'est pas pris en compte par
`/ready`. Cette route vérifie la connexion MCP et tente une récupération
bornée si nécessaire, sans appel d'outil métier.

Pour vérifier manuellement que le modèle configuré existe déjà localement :

```bash
ollama show gemma3:latest
```

Cette commande ne télécharge aucun modèle. L'intégration d'Ollama à Docker
Compose est décrite ci-dessous.

## Lancement local

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m app.main
```

## Docker

L'image de production utilise Python 3.12 slim, installe uniquement
`requirements.txt`, copie le paquet `app` et exécute Uvicorn avec un
utilisateur non privilégié. Elle ne contient ni tests, ni environnement
virtuel, ni fichier `.env`.

Depuis la racine du dépôt :

```bash
cp .env.example .env
# Remplacer les valeurs d'exemple sensibles avant le démarrage.

docker compose config --quiet
docker compose build ai-service
docker compose up -d
docker compose ps
```

Le mode Compose par défaut est `rules` et ne démarre pas Ollama. Le service IA
est publié par défaut sur `http://localhost:8001`. Le port hôte peut être
changé avec `AI_SERVICE_HOST_PORT`. Compose ordonne le démarrage du MCP avant
l'IA mais n'exige pas qu'il soit sain : `/health` reste disponible en mode
dégradé.

Contrôles HTTP :

```bash
curl --fail http://localhost:8001/health
curl --fail http://localhost:8001/ready

curl --fail \
  --header "Content-Type: application/json" \
  --data '{"question":"liste les produits"}' \
  http://localhost:8001/api/query
```

Les logs et l'arrêt propre s'obtiennent avec :

```bash
docker compose logs --no-color ai-service
docker compose down
```

`docker compose down` conserve les volumes PostgreSQL et Ollama tant que
l'option `--volumes` n'est pas ajoutée.

## Ollama optionnel avec Docker Compose

Ollama appartient au profil `ollama` et n'est jamais une dépendance de
démarrage obligatoire du service IA :

```bash
docker compose --profile ollama up -d ollama
curl --fail http://localhost:11434/api/tags
```

Le modèle doit être téléchargé explicitement par un opérateur :

```bash
docker compose --profile ollama exec ollama \
  ollama pull gemma3:latest
```

Aucun build et aucun démarrage de service n'exécute cette commande
automatiquement. Après vérification de la présence du modèle, le mode hybride
peut être activé avec :

```bash
AI_INTENT_PROVIDER=ollama \
  docker compose up -d --force-recreate ai-service
```

Si Ollama est absent, trop lent ou retourne une sortie invalide, `/api/query`
conserve la clarification déterministe. `/health` et `/ready` ne dépendent pas
de sa disponibilité.

## Flux de données Compose

```text
client HTTP
    -> ai-service:8001
    -> product-mcp-server:8000/mcp
    -> external-products-api:5000 ou backoffice:5000
    -> PostgreSQL, uniquement depuis le Backoffice
```

`ai-service` ne reçoit aucune URL, clé ou variable PostgreSQL du Backoffice.
Il contacte uniquement le serveur MCP pour les données métier. Ollama reçoit
seulement la question à classifier, jamais une réponse MCP, un produit ou un
stock.

Les erreurs de validation de `POST /api/query`, y compris un JSON malformé,
retournent HTTP `422` avec les cinq champs publics `success`, `answer`, `type`,
`data` et `error`. Aucun détail Pydantic ou contenu brut invalide n'est
exposé.

## Tests

Les tests utilisent directement l'application ASGI, des doubles injectés et
un transport officiel dirigé vers une adresse locale indisponible. Ils
n'utilisent jamais Internet :

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  -m pytest -v -p no:cacheprovider

uv pip check --python .venv/bin/python

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  -m compileall -q app tests
```

L'orchestration n'appelle jamais directement le Backoffice, l'API Produit ou
PostgreSQL. Le classificateur ne reçoit ni données MCP, ni stock, ni produit,
ni URL métier, et ses textes ne sont jamais utilisés comme réponse publique.
