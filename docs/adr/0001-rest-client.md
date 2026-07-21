# ADR 0001 — Utiliser REST pour le client web public

## Statut

Accepté

## Contexte

Le client web public doit permettre à un utilisateur anonyme d’envoyer
une question au service AI Query et d’afficher la réponse obtenue.

Deux stratégies de communication ont été envisagées :

- une API REST ;
- une connexion WebSocket.

Dans le MVP, chaque question est traitée indépendamment. Aucun historique
de conversation, streaming de réponse ou échange permanent en temps réel
n’est requis.

## Décision

Nous avons choisi d’utiliser une API REST entre le client web public
et le service AI Query.

Le client enverra les questions avec une requête HTTP `POST` et recevra
une réponse JSON.

## Raisons du choix

REST a été retenu car :

- chaque question est indépendante ;
- aucune connexion persistante n’est nécessaire ;
- aucun streaming n’est demandé dans le MVP ;
- les requêtes peuvent facilement être testées avec curl ou Postman ;
- l’intégration avec une interface HTML et JavaScript est simple ;
- cette solution réduit la complexité du projet.

## Conséquences

### Conséquences positives

- L’architecture est simple à développer et à comprendre.
- Les endpoints peuvent être testés indépendamment du client web.
- Les erreurs HTTP et JSON sont faciles à contrôler.
- Aucun mécanisme de connexion persistante n’est nécessaire.

### Conséquences négatives

- La réponse est reçue entièrement à la fin du traitement.
- Il n’y aura pas de streaming mot par mot.
- Un passage futur vers un véritable chat en temps réel pourrait
  nécessiter l’ajout de WebSocket ou d’une autre technologie de streaming.