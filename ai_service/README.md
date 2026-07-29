# Service IA HBntory

Le service FastAPI reçoit les questions du client public. Il ne contacte
directement ni PostgreSQL, ni le Backoffice, ni l’API Produit : toutes les
données métier passent par le serveur MCP et ses cinq outils en lecture seule.

## Fournisseurs

Deux modes seulement sont acceptés :

- `nvidia` — mode principal : MiniMax-M3 est appelé via l’API NVIDIA ;
- `rules` — compréhension locale et réponses déterministes.

En mode `nvidia`, une clé absente ne bloque pas le démarrage. Aucun client
externe n’est alors créé et le statut devient `fallback_rules`. Une erreur
NVIDIA attendue pendant la classification ou la rédaction déclenche également
le fallback local, sans basculer vers un autre fournisseur.

Il n’existe aucune IA locale. Le mode NVIDIA dépend d’Internet, d’une clé
NVIDIA valide et de la disponibilité de l’API NVIDIA.

## Flux d’une question

```text
Question
→ garde locale et résolution du contexte
→ classification MiniMax-M3 via NVIDIA, si disponible
→ intention Pydantic ancrée
→ zéro ou un outil MCP sélectionné par Python
→ données métier validées
→ réponse naturelle MiniMax-M3 via NVIDIA, si disponible
→ contrôle factuel structuré
→ AnswerBuilder en fallback
```

Le modèle ne reçoit aucune définition d’outil et ne peut pas faire de tool
calling. Une question peut produire au maximum :

- un appel NVIDIA de classification ;
- un appel MCP métier ;
- un appel NVIDIA de rédaction.

Une demande hors domaine, ambiguë, incomplète ou d’écriture peut être refusée
avant tout appel MCP ou NVIDIA.

## Routes

- `GET /health` — état du processus HTTP ;
- `GET /ready` — disponibilité MCP et état du fournisseur ;
- `GET /api/products` — une page du catalogue via `list_products`, sans IA ;
- `POST /api/query` — question métier et conversation.

`GET /ready` n’appelle pas NVIDIA. Les champs utiles sont :

- `provider` : mode demandé, `nvidia` ou `rules` ;
- `provider_status` : `configured`, `fallback_rules` ou `disabled` ;
- `active_provider` : `nvidia` ou `rules`.

## Conversation multi-tour

La conversation multi-tour est une fonctionnalité optionnelle ajoutée au
parcours REST initial. `POST /api/query` accepte le `conversation_id` opaque
retourné au tour précédent :

```json
{
  "question": "Où est disponible le produit 11 ?"
}
```

Puis :

```json
{
  "conversation_id": "identifiant-opaque-retourne-par-le-serveur",
  "question": "Et à Toulouse ?"
}
```

La mémoire :

- reste en RAM et disparaît au redémarrage ;
- expire après `CONVERSATION_TTL_SECONDS`, 1 800 secondes par défaut ;
- conserve au plus `CONVERSATION_MAX_TURNS`, 10 tours par défaut ;
- conserve au plus `CONVERSATION_MAX_SESSIONS`, 1 000 sessions par défaut ;
- utilise un verrou par conversation et une éviction LRU ;
- sépare strictement les identifiants de conversation.

Elle permet notamment `le deuxième`, `celui-ci`, `où puis-je le trouver ?` et
`et à Toulouse ?`. Elle ne stocke ni client HTTP, ni clé, ni objet MCP brut.

## Intentions

Les six intentions strictes sont :

- `product_list`;
- `product_details`;
- `stock_by_product`;
- `stock_by_branch`;
- `shopping_list`;
- `unsupported`.

Le résolveur local et l’ancrage Pydantic conservent les synonymes, les nombres
français courants, les noms de branche, les listes quantifiées, les références
ordinales et les pronoms. Ils n’inventent aucun identifiant.

## Réponses et contrôle factuel

`AnswerBuilder` construit d’abord une réponse déterministe depuis le résultat
MCP validé. Lorsque NVIDIA est disponible, MiniMax-M3 peut reformuler cette
réponse depuis une liste exhaustive de claims autorisés.

Le contrôle vérifie notamment :

- produit → prix et devise ;
- produit → branche ;
- branche → quantité ;
- disponibilité → quantité positive ;
- indisponibilité → absence ou quantité nulle ;
- liste d’achats → branches satisfaisantes.

Une relation ajoutée, omise, dupliquée, permutée ou contradictoire est rejetée.
La réponse déterministe est alors conservée.

## Confidentialité

NVIDIA peut recevoir :

- la question courante après redaction des marqueurs sensibles ;
- un historique récent, borné et redigé ;
- un état conversationnel réduit ;
- les claims métier nécessaires à la rédaction.

NVIDIA ne reçoit jamais :

- la clé NVIDIA ou une autre clé de service ;
- une URL interne ;
- une configuration d’infrastructure ;
- une requête SQL ou un accès PostgreSQL ;
- un objet/résultat MCP brut ;
- des en-têtes d’authentification internes ;
- un accès direct au Backoffice ou à l’API Produit.

La redaction reste une protection applicative heuristique. Les questions et
faits métier envoyés à NVIDIA doivent être considérés comme des données
transmises à un fournisseur externe.

## Configuration

```env
AI_MODEL_PROVIDER=nvidia
NVIDIA_API_KEY=
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
NVIDIA_MODEL=minimaxai/minimax-m3
NVIDIA_REQUEST_TIMEOUT_SECONDS=60
NVIDIA_CLASSIFICATION_MAX_TOKENS=600
NVIDIA_ANSWER_MAX_TOKENS=1000

AI_SERVICE_HOST=0.0.0.0
AI_SERVICE_PORT=8001
CORS_ALLOWED_ORIGINS=http://localhost:8080
MCP_SERVER_URL=http://product-mcp-server:8000/mcp
MCP_REQUEST_TIMEOUT_SECONDS=10
MCP_MAX_CONCURRENT_CALLS=10
MCP_RECONNECT_ATTEMPTS=3
MCP_RECONNECT_INITIAL_DELAY_SECONDS=0.25
MCP_RECONNECT_MAX_DELAY_SECONDS=2
CONVERSATION_TTL_SECONDS=1800
CONVERSATION_MAX_TURNS=10
CONVERSATION_MAX_SESSIONS=1000
```

Toute autre valeur de `AI_MODEL_PROVIDER` est rejetée au chargement de la
configuration. Une valeur vide de `NVIDIA_API_KEY` équivaut à une clé absente.

## Installation et lancement

```bash
cd ai_service
uv venv .venv --python 3.12
uv pip install \
  --python .venv/bin/python \
  -r requirements.txt \
  -r requirements-dev.txt

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m app.main
```

L’image Docker de production installe uniquement `requirements.txt`, copie
uniquement `app/` et fonctionne avec l’utilisateur non-root `ai-service`.

## Tests

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  -m pytest -v -p no:cacheprovider

.venv/bin/python -m compileall -q app
uv pip check --python .venv/bin/python
```

Tous les appels NVIDIA sont simulés dans les tests. Un test réel exige une clé,
un accès Internet et un compte NVIDIA autorisé pour
`minimaxai/minimax-m3`.
