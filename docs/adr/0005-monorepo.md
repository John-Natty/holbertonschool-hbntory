# ADR 0005 — Organiser le projet en monorepo multi-services

## Statut

Accepté

## Contexte

HBntory est composé de plusieurs composants ayant des responsabilités
distinctes :

- un Backoffice Flask ;
- une base de données PostgreSQL ;
- un serveur MCP ;
- un service IA indépendant ;
- un client web public ;
- une API Produit externe fournie avec le projet.

Les différents services doivent être développés, testés et exécutés ensemble
pour permettre le fonctionnement complet de l’application et sa démonstration
finale.

Deux stratégies principales ont été envisagées :

- créer un dépôt Git indépendant pour chaque service ;
- regrouper les services dans un seul dépôt Git, avec un dossier distinct pour
  chaque composant.

Même si les services appartiennent au même projet, ils doivent conserver des
frontières techniques claires et communiquer uniquement à travers leurs
interfaces réseau.

## Décision

Nous utilisons un monorepo multi-services.

Tous les composants développés par l’équipe sont regroupés dans un seul dépôt
Git.

Chaque service conserve néanmoins :

- son propre dossier ;
- son propre code applicatif ;
- ses propres modèles ;
- ses propres dépendances ;
- ses propres tests ;
- son propre fichier Dockerfile lorsque nécessaire ;
- son propre cycle de démarrage ;
- ses propres responsabilités métier.

Les services communiquent uniquement à travers des interfaces réseau
documentées :

- HTTP et REST ;
- MCP Streamable HTTP ;
- connexion SQL uniquement entre le Backoffice et PostgreSQL.

Aucun service ne doit importer directement le code métier d’un autre service.

Par exemple :

- le service IA n’importe pas les modèles SQLAlchemy du Backoffice ;
- le serveur MCP n’accède pas directement à PostgreSQL ;
- le client web ne contacte pas directement le MCP ou la base de données ;
- le Backoffice ne dépend pas du code Python du service IA.

## Structure actuelle

```text
holbertonschool-hbntory/
├── backoffice/
│   ├── app/
│   │   ├── admin/
│   │   ├── auth/
│   │   ├── internal_api/
│   │   ├── models/
│   │   ├── services/
│   │   ├── stock/
│   │   ├── static/
│   │   └── templates/
│   ├── migrations/
│   ├── tests/
│   ├── seed.py
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   └── Dockerfile
│
├── product_mcp_server/
│   ├── clients/
│   ├── models/
│   ├── tools/
│   ├── tests/
│   ├── server.py
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   └── Dockerfile
│
├── ai_service/
│   ├── app/
│   │   ├── api/
│   │   ├── clients/
│   │   ├── models/
│   │   └── services/
│   ├── tests/
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   ├── README.md
│   └── Dockerfile
│
├── client_web/
│   ├── img/
│   ├── index.html
│   ├── style.css
│   ├── script.js
│   ├── background.js
│   └── Dockerfile
│
├── docs/
│   ├── adr/
│   ├── architecture.md
│   ├── authentication.md
│   └── mvp.md
│
├── docker-compose.yml
├── docker-compose.test.yml
├── .env.example
├── .gitignore
└── README.md
```

Cette structure représente l’organisation actuelle du dépôt. Elle peut évoluer
si de nouveaux besoins apparaissent, à condition de conserver la séparation
des responsabilités entre les services.

## Responsabilités des composants

### Backoffice

Le Backoffice est responsable :

- de l’authentification des utilisateurs internes ;
- de la gestion des rôles ;
- de la gestion des utilisateurs common ;
- de l’affectation des utilisateurs aux branches ;
- de la consultation et de la modification des stocks ;
- de l’accès à PostgreSQL avec SQLAlchemy ;
- de l’exposition d’une API interne de consultation du stock.

Le Backoffice est le seul service applicatif autorisé à accéder directement à
PostgreSQL.

### PostgreSQL

PostgreSQL stocke uniquement les données locales :

- utilisateurs ;
- branches ;
- quantités de stock par branche et par identifiant Produit.

Les noms, descriptions, prix, images et métadonnées des produits ne sont pas
stockés localement.

### API Produit externe

L’API Produit est la source de vérité pour les informations Produit :

- identifiant ;
- nom ;
- description ;
- catégorie ;
- marque ;
- fournisseur ;
- prix ;
- devise ;
- autres métadonnées.

Elle est utilisée par le Backoffice et par le serveur MCP lorsque des
informations Produit sont nécessaires.

### Serveur MCP

Le serveur MCP agit comme une frontière contrôlée entre le service IA et les
sources de données.

Il expose exactement cinq outils en lecture seule :

- `list_products` ;
- `get_product_details` ;
- `get_stock_by_product` ;
- `get_stock_by_branch` ;
- `check_shopping_list`.

Il communique avec :

- l’API Produit externe ;
- l’API interne du Backoffice.

Il ne se connecte jamais directement à PostgreSQL.

### Service IA

Le service IA est un service FastAPI indépendant.

Il est responsable :

- de recevoir les questions du client public ;
- de comprendre les intentions utilisateur ;
- de gérer le contexte conversationnel facultatif ;
- de sélectionner au maximum un outil MCP par question ;
- de valider les données retournées ;
- de construire une réponse naturelle et factuellement contrôlée.

Le fournisseur principal est MiniMax-M3 via l’API NVIDIA.

Un mode local basé sur les règles Python et `AnswerBuilder` reste disponible
comme solution de secours.

Le service IA n’accède directement ni à PostgreSQL, ni au Backoffice, ni à
l’API Produit.

### Client web public

Le client web est une interface publique sans authentification.

Il permet :

- de consulter le catalogue ;
- d’envoyer des questions en langage naturel ;
- d’afficher les réponses ;
- de poursuivre une conversation grâce à un `conversation_id` ;
- d’afficher les erreurs et les états de chargement.

Il communique uniquement avec le service IA par REST.

## Communications entre les services

Le flux du Backoffice est :

```text
Navigateur interne
→ Backoffice Flask
→ SQLAlchemy
→ PostgreSQL
```

Lorsque des informations Produit sont nécessaires :

```text
Backoffice
→ API Produit externe
```

Le flux du client public est :

```text
Navigateur public
→ Service IA
→ Serveur MCP
→ API Produit externe
```

ou, pour les informations de stock :

```text
Navigateur public
→ Service IA
→ Serveur MCP
→ API interne du Backoffice
→ PostgreSQL
```

Le flux de communication entre les services reste contrôlé par des contrats
réseau explicites.

## Orchestration avec Docker Compose

Le dépôt contient un fichier `docker-compose.yml` permettant de démarrer les
services nécessaires :

- l’API Produit externe ;
- PostgreSQL ;
- le Backoffice ;
- le serveur MCP ;
- le service IA ;
- le client web.

Docker Compose fournit :

- un réseau commun entre les services ;
- la résolution des noms de services ;
- les variables d’environnement ;
- les dépendances de démarrage ;
- les healthchecks ;
- le volume persistant de PostgreSQL.

MiniMax-M3 est fourni par une API NVIDIA externe et ne nécessite aucun
conteneur local.

Un fichier `docker-compose.test.yml` séparé est utilisé pour les tests
Backoffice avec une base PostgreSQL isolée.

## Raisons du choix

Le monorepo a été retenu car :

- tous les services appartiennent au même projet ;
- les changements d’architecture peuvent être coordonnés dans une seule
  branche ;
- les contrats entre les services sont plus faciles à suivre ;
- Docker Compose peut être maintenu à la racine ;
- la documentation globale est regroupée ;
- les tests peuvent être lancés depuis un seul dépôt ;
- la démonstration complète est plus simple à préparer ;
- cette organisation convient à une équipe de taille limitée ;
- elle évite la gestion de plusieurs dépôts, versions et permissions.

Le monorepo ne signifie pas que les services forment une application monolithique.
Chaque composant conserve ses propres frontières et communique par le réseau.

## Conséquences

### Conséquences positives

- Le projet complet peut être cloné avec une seule commande.
- La configuration Docker est centralisée.
- Les décisions d’architecture sont documentées au même endroit.
- Les changements affectant plusieurs services peuvent être coordonnés.
- Les tests de chaque service restent séparés.
- Les dépendances Python ne sont pas mélangées entre les services.
- Les services peuvent être construits et exécutés indépendamment.
- Les contrats réseau restent visibles et vérifiables.
- La préparation de la démonstration est simplifiée.

### Conséquences négatives

- Le dépôt contient plusieurs technologies et devient plus volumineux.
- Une modification globale peut toucher plusieurs services.
- Les règles Git doivent être respectées pour éviter les conflits entre les
  membres de l’équipe.
- Les pipelines de tests doivent distinguer les différents services.
- Les fichiers de configuration communs, comme Docker Compose, peuvent devenir
  des points de conflit.
- Une mauvaise organisation pourrait créer des dépendances directes entre les
  services.

## Règles de séparation

Pour préserver l’indépendance des services :

- chaque service possède ses propres dépendances ;
- chaque service possède ses propres tests ;
- les imports Python entre services sont interdits ;
- les échanges métier utilisent HTTP, REST ou MCP ;
- les secrets sont fournis par variables d’environnement ;
- PostgreSQL n’est accessible directement que par le Backoffice ;
- les informations Produit proviennent toujours de l’API externe ;
- le service IA passe obligatoirement par le MCP pour les données métier ;
- les modifications d’un contrat réseau doivent être documentées et testées.

## Alternatives rejetées

### Un dépôt Git par service

Cette organisation aurait permis une isolation plus forte et des cycles de
version indépendants.

Elle n’a pas été retenue car :

- elle aurait multiplié les dépôts à maintenir ;
- elle aurait compliqué les modifications touchant plusieurs services ;
- elle aurait demandé une gestion supplémentaire des versions ;
- elle aurait rendu la configuration Docker globale moins pratique ;
- elle n’apportait pas de bénéfice suffisant pour la taille du projet et de
  l’équipe.

### Application monolithique

Une seule application aurait pu contenir le Backoffice, l’IA, le MCP et le
client.

Cette solution n’a pas été retenue car :

- elle aurait mélangé les responsabilités ;
- elle aurait permis des accès directs non contrôlés aux données ;
- elle aurait rendu l’intégration MCP moins claire ;
- elle aurait réduit l’indépendance du service IA ;
- elle aurait été moins conforme à l’objectif pédagogique d’une architecture
  multi-services.

## Limites

Le monorepo facilite le développement en équipe, mais il ne remplace pas une
gestion claire des responsabilités.

Les services restent indépendants au niveau applicatif, même s’ils partagent :

- le même dépôt Git ;
- le même fichier Docker Compose ;
- la même documentation globale ;
- le même réseau Docker pendant l’exécution.
