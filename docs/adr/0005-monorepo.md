# ADR 0005 — Organiser le projet en monorepo multi-services

## Statut

Accepté

## Contexte

HBntory est composé de plusieurs services indépendants :

- un Backoffice ;
- une base de données PostgreSQL ;
- un serveur MCP ;
- un service AI Query ;
- un client web public ;
- une API Produit externe fournie avec le projet.

Le projet est réalisé en équipe de deux personnes dans un délai limité.

Deux stratégies principales ont été envisagées :

- créer un dépôt Git séparé pour chaque service ;
- regrouper les services dans un seul dépôt Git avec des dossiers distincts.

Même si les services ont des responsabilités différentes, ils doivent
être développés, testés et lancés ensemble pour la démonstration finale.

## Décision

Nous avons choisi une organisation en monorepo multi-services.

Tous les composants développés par l’équipe seront regroupés dans un seul
dépôt Git.

Chaque service conservera cependant :

- son propre dossier ;
- ses propres dépendances ;
- ses propres tests ;
- son propre fichier Dockerfile ;
- ses propres responsabilités.

Les services communiqueront par des interfaces réseau, telles que HTTP,
REST ou MCP.

Ils ne devront pas effectuer d’import direct depuis le code d’un autre
service.

## Structure prévue

```text
hbntory/
├── backoffice/
│   ├── app/
│   ├── tests/
│   ├── migrations/
│   ├── requirements.txt
│   └── Dockerfile
│
├── product_mcp_server/
│   ├── clients/
│   ├── tools/
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
│
├── ai_service/
│   ├── agents/
│   ├── clients/
│   ├── routes/
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
│
├── client_web/
│   ├── index.html
│   ├── style.css
│   ├── script.js
│   └── Dockerfile
│
├── docs/
│   ├── architecture.md
│   └── adr/
│
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md