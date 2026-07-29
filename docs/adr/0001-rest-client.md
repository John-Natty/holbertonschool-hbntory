# ADR 0001 — Utiliser REST pour le client web public

## Statut

Accepté

## Contexte

Le client web public permet à un utilisateur anonyme d’envoyer une question au
service IA et d’afficher la réponse obtenue.

Deux stratégies de communication ont été envisagées :

- une API REST ;
- une connexion WebSocket.

Le fonctionnement obligatoire du MVP ne nécessite ni streaming, ni connexion
permanente, ni réponse en temps réel.

Une conversation multi-tour volatile a ensuite été ajoutée comme fonctionnalité
optionnelle. Cette évolution reste compatible avec REST : le serveur génère un
identifiant opaque de conversation et le client le transmet dans les requêtes
suivantes.

## Décision

Nous utilisons une API REST entre le client web public et le service IA.

Le client envoie une question avec la requête suivante :

```http
POST /api/query
```

Lors du premier échange, la requête peut contenir uniquement la question :

```json
{
  "question": "Où est disponible le produit 11 ?"
}
```

Le service retourne une réponse JSON contenant notamment :

- la réponse destinée à l’utilisateur ;
- le type de demande détecté ;
- les données métier validées ;
- un identifiant opaque `conversation_id`.

Exemple simplifié :

```json
{
  "conversation_id": "identifiant-opaque",
  "success": true,
  "answer": "Le produit 11 est disponible à Carcassonne.",
  "type": "stock_by_product",
  "data": {},
  "error": null
}
```

Pour poursuivre la même conversation, le client renvoie le
`conversation_id` reçu précédemment :

```json
{
  "conversation_id": "identifiant-opaque",
  "question": "Et à Toulouse ?"
}
```

Chaque message reste une requête HTTP indépendante. Le contexte conversationnel
est retrouvé côté serveur grâce au `conversation_id`, sans maintenir de
connexion réseau permanente.

Le client utilise également une route REST séparée pour charger le catalogue :

```http
GET /api/products
```

Cette route retourne directement des données structurées et n’utilise pas le
fournisseur IA.

## Raisons du choix

REST a été retenu pour les raisons suivantes :

- chaque échange reste une requête HTTP indépendante ;
- aucune connexion persistante n’est nécessaire ;
- aucun streaming n’est exigé dans le MVP ;
- les requêtes sont simples à tester avec `curl`, Postman ou des tests
  automatisés ;
- l’intégration avec une interface HTML, CSS et JavaScript est simple ;
- les erreurs peuvent être représentées avec des codes HTTP et des réponses
  JSON structurées ;
- une conversation multi-tour peut être gérée avec un identifiant transmis dans
  le corps JSON ;
- cette solution réduit la complexité de développement et de déploiement.

## Conséquences

### Conséquences positives

- L’architecture est simple à développer et à comprendre.
- Le client et le service IA restent faiblement couplés.
- Les endpoints peuvent être testés indépendamment du navigateur.
- Les erreurs HTTP et JSON sont faciles à contrôler.
- Aucun mécanisme de connexion persistante n’est nécessaire.
- Le client peut poursuivre une conversation en réutilisant un identifiant
  opaque.
- Une question peut toujours être traitée sans historique lorsque le
  `conversation_id` est absent.
- La route du catalogue reste indépendante de la génération par IA.

### Conséquences négatives

- La réponse est reçue entièrement à la fin du traitement.
- Il n’existe pas de streaming mot par mot.
- Chaque nouveau message nécessite une nouvelle requête HTTP.
- La mémoire conversationnelle est stockée uniquement dans la RAM du service
  IA.
- Le contexte disparaît après expiration, redémarrage du service ou suppression
  de la session.
- Plusieurs instances du service IA nécessiteraient un stockage partagé pour
  conserver la continuité des conversations.
- Un futur besoin de streaming pourrait nécessiter SSE, WebSocket ou une autre
  technologie adaptée.

## Alternatives rejetées

### WebSocket

WebSocket permettrait une connexion persistante, des réponses progressives et
des échanges en temps réel.

Cette solution n’a pas été retenue car :

- le MVP ne demande pas de streaming ;
- les échanges restent simples et déclenchés par l’utilisateur ;
- la gestion des connexions persistantes augmenterait inutilement la
  complexité ;
- REST suffit pour transmettre un `conversation_id` et maintenir un contexte
  multi-tour limité.

## Fonctionnalité optionnelle

La mémoire conversationnelle n’est pas une exigence obligatoire de l’énoncé.

Elle a été ajoutée comme amélioration afin de permettre des échanges tels que :

```text
Utilisateur : Où est disponible le produit 11 ?
Assistant : Le produit 11 est disponible à Carcassonne.

Utilisateur : Et à Toulouse ?
Assistant : Le produit 11 n’est pas disponible à Toulouse.
```

Cette mémoire reste volontairement :

- volatile ;
- limitée dans le temps ;
- limitée en nombre de tours ;
- séparée par conversation ;
- sans stockage persistant.
