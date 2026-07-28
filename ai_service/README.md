# Service IA HBntory

Ce service expose l’API REST asynchrone utilisée par le futur client web.
Il est indépendant du Backoffice, de PostgreSQL et de l’API Produit.

## État actuel

Le service possède un client officiel MCP Streamable HTTP. Une seule session
active est partagée pendant le lifespan FastAPI et vérifie les cinq outils
attendus. Si elle est perdue, elle est fermée puis remplacée par une
reconnexion bornée et synchronisée.

`POST /api/query` accepte une question seule ou une question accompagnée du
`conversation_id` retourné au tour précédent. Une mémoire courte en RAM permet
de résoudre les références utiles (`le deuxième`, `celui-ci`, `et à
Toulouse ?`) sans conserver les réponses MCP brutes. Pydantic valide le
contrat, l'état résolu et les paramètres métier. L'orchestrateur Python choisit
seul l'un des cinq outils MCP et effectue au maximum un appel métier par
message.

Lorsque `AI_MODEL_PROVIDER=minimax`, MiniMax-M3 est le fournisseur principal :
une première complétion au maximum comprend la question et son contexte borné,
puis une seconde au maximum rédige la réponse depuis les seuls faits validés.
Le modèle ne fait jamais de tool calling. Si le fournisseur est absent,
indisponible ou produit une sortie invalide, le résolveur local minimal et
`AnswerBuilder` assurent un fallback déterministe.

Le modèle ne possède aucun mécanisme de tool calling dans HBntory et ne
reçoit aucune URL interne, clé de service ou configuration. Les gardes locales
refusent d'abord les écritures et le hors domaine. Les relations factuelles
structurées de chaque réponse générée sont ensuite comparées aux données
validées ; une relation ajoutée, oubliée, dupliquée ou permutée est rejetée.
`AnswerBuilder` remplace toute rédaction indisponible ou invalide. Les pages de
plus de dix produits conservent volontairement la liste déterministe complète :
cela évite une longue génération et garantit qu'aucune ligne ne soit oubliée.

Les réponses de stock par branche affichent le numéro, la quantité, le nom
officiel et le prix unitaire de chaque produit. Le même outil
`get_stock_by_branch` récupère la quantité auprès du Backoffice puis enrichit
chaque ligne avec l'API Produit. Le contrat MCP retourne `product_id`,
`product_name`, `unit_price`, `currency` et `quantity`. Cette mise en forme ne
déclenche jamais de second appel MCP et n'invente aucune donnée produit.

Routes disponibles :

- `GET /health` : état du processus HTTP ;
- `GET /ready` : disponibilité de la session MCP, avec `200` ou `503` ;
- `GET /api/products` : chargement structuré et déterministe du catalogue ;
- `POST /api/query` : validation et traitement injectable d'une question.

## Conversation multi-tour

Une première requête reste compatible avec le contrat historique :

```json
{
  "question": "Où est disponible le produit 11 ?"
}
```

Le serveur crée un identifiant opaque et le retourne dans toutes les variantes
de réponse :

```json
{
  "conversation_id": "b0d85946-4a3c-4fb5-87c9-2dcd77fe90d2",
  "success": true,
  "answer": "Le produit 11 est disponible à Carcassonne avec 10 unités.",
  "type": "stock_by_product",
  "data": {
    "product_id": 11,
    "branches": [
      {
        "branch_id": 2,
        "branch_name": "Carcassonne",
        "quantity": 10
      }
    ]
  },
  "error": null
}
```

Le tour suivant renvoie cet identifiant :

```json
{
  "conversation_id": "b0d85946-4a3c-4fb5-87c9-2dcd77fe90d2",
  "question": "Et à Toulouse ?"
}
```

L'identifiant est généré aléatoirement côté serveur, ne contient aucune donnée
utilisateur et ne doit pas être construit à partir d'un nom, d'une adresse ou
d'un secret. Un identifiant vide, mal formé ou trop long est refusé.

La mémoire est volontairement locale au processus et volatile :

- expiration après `CONVERSATION_TTL_SECONDS=1800` secondes d'inactivité ;
- au plus `CONVERSATION_MAX_TURNS=10` tours récents par conversation ;
- au plus `CONVERSATION_MAX_SESSIONS=1000` conversations, avec éviction des
  moins récemment utilisées ;
- verrou distinct par conversation afin de sérialiser deux messages reçus en
  même temps sans bloquer les autres conversations ;
- aucun secret, client HTTP, objet MCP, réponse MCP brute ou donnée PostgreSQL
  n'est stocké.

L'état mémorisé se limite aux derniers messages bornés, à la dernière
intention, au produit et à la branche utiles, aux identifiants d'une liste
affichée, à la liste d'achats courante et à quelques résultats métier réduits.
Deux identifiants différents ne partagent jamais leur état. Une expiration ou
un redémarrage efface le contexte. Si le client renvoie ensuite un identifiant
devenu inconnu, le serveur le remplace par un nouvel identifiant aléatoire ;
une référence devenue impossible à résoudre provoque alors une demande de
clarification.

## Questions en langage naturel

L'utilisateur écrit sa demande avec ses propres mots. Les termes `article`,
`référence`, `matériel` et `marchandise` peuvent désigner un produit ; les
termes `agence`, `boutique`, `magasin` et `dépôt` peuvent désigner une branche.
Le système conserve six intentions strictes :

- `product_list` : parcourir le catalogue, avec pagination facultative ;
- `product_details` : demander les informations, le prix, la description,
  la marque, la catégorie ou le fournisseur d'un produit ;
- `stock_by_product` : demander où un produit est disponible ;
- `stock_by_branch` : demander ce que contient une branche ou un dépôt,
  désigné par son identifiant ou par son nom ;
- `shopping_list` : liste explicite d'identifiants et de quantités ;
- `unsupported` : demande inconnue, incomplète ou contradictoire.

Le rôle d'un nombre dépend de la structure de la phrase :

```text
les 10 premiers produits
    -> product_list, limit=10

le produit 10
    -> product_details, product_id=10
```

Cette distinction fonctionne également avec `dix produits`, `produit dix` et
`article numéro dix`. Le mot `détails` ne suffit jamais à transformer une
demande portant sur plusieurs produits en détail d'un seul produit.

Une branche peut être demandée naturellement, par exemple avec `stock de
Toulouse`, `inventaire du site Toulouse` ou `liste les produits de la branche
Carcassonne`. La présence d'une branche explicite impose l'intention
`stock_by_branch`, même si la phrase contient `liste les produits`; elle ne
doit pas charger le catalogue général. L'intention transporte alors
`branch_name`, sans inventer de `branch_id`. Le même outil MCP
`get_stock_by_branch` accepte exactement une référence : `branch_id` ou
`branch_name`. Avec un nom, le MCP utilise la route interne protégée
`GET /internal/stocks/branches/by-name?name=...`. Le Backoffice résout le nom
réel sans tenir compte de la casse, après normalisation des espaces.

Exemple de réponse :

```text
La branche Toulouse possède 1 référence en stock :
- Produit n°1 — Quantité : 5 — Nom : Holberton Student Laptop 14 — Prix unitaire : 799,00 USD
```

Pour une intention `product_list`, `answer` présente chaque produit de la page
avec son identifiant, son nom, son prix et sa devise. Ces lignes utilisent
uniquement la réponse de `list_products` et ne déclenchent aucun appel de
détail supplémentaire.

Une liste d'achats peut également être formulée naturellement, tant que chaque
identifiant est associé à une quantité explicite, écrite en chiffres ou avec
un petit nombre en français, par exemple :

```text
liste d'achats : produit 12 x2, produit 7 x1
vérifie la liste : 12 x2, 7 x1
où acheter 12 x2 et 7 x1
quelle branche peut fournir deux produits 4 et un produit 8 ?
```

Les identifiants et quantités doivent être des entiers strictement positifs.
Les doublons d'un même produit sont additionnés en conservant l'ordre de sa
première occurrence. Un nom de produit n'est jamais converti en identifiant.

Une question incomplète, telle que `stock de la branche`, ou une demande
contenant plusieurs actions retourne une clarification de type `unsupported`
sans appel MCP. Il en va de même pour une question hors domaine ou une demande
d'écriture : le refus reste déterministe et aucun outil MCP n'est appelé.

## Chargement technique du catalogue

Le client web peut charger le catalogue indépendamment d'une question libre :

```http
GET /api/products?limit=100&offset=0
```

`limit` vaut `100` par défaut et doit rester entre `1` et `100`. `offset` vaut
`0` par défaut et doit être positif ou nul. La réponse réutilise le contrat
MCP `ProductListData` :

```json
{
  "success": true,
  "data": {
    "count": 1,
    "limit": 100,
    "offset": 0,
    "products": [
      {
        "id": 4,
        "sku": "HB-MON-2102",
        "name": "24 inch Compact Monitor",
        "description": "Training catalog item.",
        "category": "Displays",
        "brand": "LabForge",
        "supplier_id": "SUP-LAB-002",
        "supplier_name": "LabForge Supplies",
        "unit_price": 169.99,
        "currency": "USD",
        "discontinued": false,
        "weight_kg": 3.9,
        "tags": ["display", "compact"],
        "updated_at": "2026-05-22T12:00:00Z",
        "supplier": null
      }
    ]
  },
  "error": null
}
```

Cette route emploie le client MCP partagé et appelle exactement une fois
`list_products`. Elle ne passe ni par le routeur d'intentions, ni par MiniMax,
ni par Ollama, ni par `AnswerBuilder`, et ne constitue pas un sixième outil
MCP.

La séparation publique est donc :

```text
chargement automatique du catalogue
    -> GET /api/products
    -> MCP list_products, sans classification

question rédigée par l'utilisateur
    -> POST /api/query
    -> compréhension libre puis zéro ou un appel MCP
```

## Codes HTTP publics

- `200` : résultat MCP validé ou clarification sans donnée métier ;
- `404` : produit ou branche absent ;
- `422` : requête ou paramètres invalides, avec un `ErrorResponse` stable ;
- `502` : réponse MCP invalide ou autre erreur métier contrôlée ;
- `503` : serveur MCP indisponible ;
- `504` : délai MCP dépassé ;
- `500` : bug inattendu, avec un corps générique sans détail interne.

Pour `GET /api/products`, une page vide reste un succès `200`. Une pagination
invalide retourne `422` avant tout appel MCP et une indisponibilité MCP
retourne une erreur structurée `503`.

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
CONVERSATION_TTL_SECONDS=1800
CONVERSATION_MAX_TURNS=10
CONVERSATION_MAX_SESSIONS=1000
MCP_SERVER_URL=http://product-mcp-server:8000/mcp
MCP_REQUEST_TIMEOUT_SECONDS=10
MCP_MAX_CONCURRENT_CALLS=10
MCP_RECONNECT_ATTEMPTS=3
MCP_RECONNECT_INITIAL_DELAY_SECONDS=0.25
MCP_RECONNECT_MAX_DELAY_SECONDS=2
AI_MODEL_PROVIDER=hybrid
NVIDIA_API_KEY=
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
NVIDIA_MODEL=minimaxai/minimax-m3
NVIDIA_REQUEST_TIMEOUT_SECONDS=120
NVIDIA_CLASSIFICATION_MAX_TOKENS=600
NVIDIA_ANSWER_MAX_TOKENS=1000
MINIMAX_API_KEY=
MINIMAX_BASE_URL=https://api.minimax.io/v1
MINIMAX_MODEL=MiniMax-M3
MINIMAX_REQUEST_TIMEOUT_SECONDS=60
MINIMAX_CLASSIFICATION_MAX_TOKENS=600
MINIMAX_ANSWER_MAX_TOKENS=1000
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODEL=gemma3:latest
OLLAMA_REQUEST_TIMEOUT_SECONDS=60
OLLAMA_CLASSIFICATION_MAX_TOKENS=600
OLLAMA_ANSWER_MAX_TOKENS=1000
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

`AI_MODEL_PROVIDER` accepte :

- `hybrid` : sélectionne NVIDIA comme fournisseur unique si sa clé existe,
  sinon Ollama ; aucune cascade de fournisseurs n'est effectuée par message ;
- `nvidia` : utilise `minimaxai/minimax-m3` via NVIDIA pour comprendre puis
  rédiger si sa clé existe, sinon reste sur les fallbacks locaux ;
- `minimax` : MiniMax-M3 comprend le message avec l'historique borné et rédige
  la réponse finale ; le service effectue au maximum deux appels MiniMax par
  message ;
- `rules` : compréhension locale minimale et réponses `AnswerBuilder`, sans
  fournisseur ;
- `ollama` : utilise Ollama comme fournisseur unique pour comprendre puis
  rédiger.

Le fournisseur est choisi une seule fois pendant le lifespan et son client
HTTP asynchrone est partagé jusqu'à l'arrêt. Les gardes locales sont appliquées
avant le modèle. Pour une demande métier, le budget maximal est une complétion
de compréhension, un appel MCP et une complétion de rédaction. Une panne ou
une sortie invalide active le fallback local, sans tenter un second
fournisseur.

Le client HTTP asynchrone NVIDIA utilise l'interface Chat Completions
compatible OpenAI sur
`https://integrate.api.nvidia.com/v1/chat/completions`. Il est créé une fois
pendant le lifespan, partagé puis fermé à l'arrêt. Il utilise `max_tokens`
conformément au contrat NVIDIA et n'envoie jamais de champ `tools` ou
`tool_choice`.

Avec une clé NVIDIA configurée, le même client partagé sert à la compréhension
puis à la rédaction structurée, soit au maximum deux complétions par message.
Sans clé ou en cas de sortie invalide, le fallback local et `AnswerBuilder`
restent disponibles sans erreur non structurée.

L'endpoint NVIDIA Build est adapté au prototypage et peut être soumis à des
quotas ou à une forte latence. Il évite le solde MiniMax direct, mais exige
tout de même une clé NVIDIA personnelle. Le délai par défaut est donc de
120 secondes. Une erreur, une limite de requêtes ou une indisponibilité active
automatiquement les réponses déterministes sans rendre le service inutilisable.

`GET /ready` n'appelle pas le fournisseur et ne consomme aucun crédit. Son
champ `provider_status` vaut `configured`, `fallback_rules` ou `disabled`. La
disponibilité globale reste fondée sur MCP, car les fallbacks permettent au
service de fonctionner sans fournisseur distant. Le champ `provider` conserve
le mode demandé et `active_provider` indique le choix réellement construit :
`nvidia`, `minimax`, `ollama` ou `rules`.

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

Le mode Compose par défaut est `hybrid`. Il démarre Ollama, attend son
healthcheck, puis lance le service IA. Une `NVIDIA_API_KEY` configurée
sélectionne NVIDIA comme fournisseur unique ; sans clé, Ollama est sélectionné.
Le service IA est publié par défaut sur `http://localhost:8001`. Le port hôte
peut être changé avec `AI_SERVICE_HOST_PORT`.

Contrôles HTTP :

```bash
curl --fail http://localhost:8001/health
curl --fail http://localhost:8001/ready

curl --fail \
  "http://localhost:8001/api/products?limit=100&offset=0"

curl --fail \
  --header "Content-Type: application/json" \
  --data '{"question":"liste les produits"}' \
  http://localhost:8001/api/query
```

Pour tester un second tour, recopier uniquement le `conversation_id` public
retourné par la première réponse :

```bash
curl --fail \
  --header "Content-Type: application/json" \
  --data \
  '{"conversation_id":"<id-retourne>","question":"Et à Toulouse ?"}' \
  http://localhost:8001/api/query
```

Les logs et l'arrêt propre s'obtiennent avec :

```bash
docker compose logs --no-color ai-service
docker compose down
```

`docker compose down` conserve les volumes PostgreSQL et Ollama tant que
l'option `--volumes` n'est pas ajoutée.

## Modèle Ollama local

Ollama démarre avec la pile Compose et conserve ses modèles dans
`ollama-data`. Vérifier les modèles disponibles :

```bash
docker compose exec ollama ollama list
```

Le modèle doit être téléchargé explicitement par un opérateur :

```bash
docker compose exec ollama \
  ollama pull gemma3:latest
```

Aucun build et aucun démarrage de service ne télécharge un modèle
automatiquement. Si Ollama est trop lent ou retourne une sortie invalide, le
fallback local prend en charge la compréhension simple et `AnswerBuilder`
conserve une réponse déterministe. Aucun autre fournisseur n'est appelé
pendant ce message.

## Flux de données Compose

```text
client HTTP
    -> ai-service:8001
    -> product-mcp-server:8000/mcp
    -> external-products-api:5000 ou backoffice:5000
    -> PostgreSQL, uniquement depuis le Backoffice
```

`ai-service` ne reçoit aucune URL, clé ou variable PostgreSQL du Backoffice.
Il contacte uniquement le serveur MCP pour les données métier. Le fournisseur
configuré reçoit un historique court, l'état conversationnel réduit, la
question courante et, pour la rédaction seulement, une projection nettoyée
des données validées. Aucun modèle ne reçoit `INTERNAL_API_KEY`, une URL
interne, un en-tête MCP, une trace brute, un objet de session ou une réponse
MCP brute. Les messages historiques sont explicitement traités comme des
données non fiables et leur taille est bornée.

Les erreurs de validation de `POST /api/query`, y compris un JSON malformé,
retournent HTTP `422` avec les six champs publics `conversation_id`, `success`,
`answer`, `type`, `data` et `error`. Aucun détail Pydantic ou contenu brut
invalide n'est exposé.

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
PostgreSQL. Tous les appels Ollama, NVIDIA et MiniMax sont simulés dans les
tests : aucune vraie clé et aucun quota ne sont utilisés. Les tests vérifient
également la sélection unique du fournisseur, les fallbacks, les relations
factuelles, l'absence de tool calling et les limites d'appels.
