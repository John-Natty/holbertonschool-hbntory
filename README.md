# HBntory

## Overview

HBntory est une plateforme d'inventaire multi-branches composée d'un
Backoffice Flask authentifié, d'un serveur MCP en lecture seule, d'un service
IA FastAPI et d'un client web public.

## Résumé de l'architecture

Le client interroge uniquement le service IA. L'IA utilise uniquement les cinq
outils du serveur MCP. Le MCP lit les produits depuis l'API Produit officielle
et les stocks depuis l'API interne protégée du Backoffice. Seul le Backoffice
accède à PostgreSQL.

Voir [docs/architecture.md](docs/architecture.md) pour les diagrammes, les
contrats et les règles de propriété des données.

## Installation

Prérequis : Docker Compose, Python 3.12, Node.js pour le contrôle syntaxique du
client et `uv` pour les environnements Python locaux.

```bash
cp .env.example .env
# Remplacer uniquement dans .env les valeurs d'exemple sensibles.
```

Pour développer et tester un service Python :

```bash
cd backoffice
python3 -m venv .venv
uv pip install \
  --python .venv/bin/python \
  -r requirements.txt \
  -r requirements-dev.txt
```

La même commande s'applique à `product_mcp_server`. Le service IA possède déjà
ses fichiers `requirements.txt` et `requirements-dev.txt` séparés.

## Lancement des services

Le mode Compose par défaut démarre PostgreSQL, l'API Produit, le Backoffice,
le serveur MCP, Ollama, le service IA hybride et le client web :

```bash
cp .env.example .env
# Remplacer les valeurs d'exemple sensibles.

docker compose up -d
docker compose ps
```

Le service IA est ensuite accessible sur `http://localhost:8001` et sa route
publique de question est `POST /api/query`. Le client web de développement
est servi depuis `http://localhost:8080`, origine autorisée par défaut via
`CORS_ALLOWED_ORIGINS`. Le modèle local configuré est `gemma3:latest`.

## Initialisation de la base de données

Le Backoffice applique automatiquement les migrations au démarrage. Après son
healthcheck, le seed initial peut être exécuté plusieurs fois sans doublon :

```bash
docker compose exec backoffice python seed.py
```

Le seed crée les deux branches configurées et au plus un administrateur.

## Accès au Backoffice

Le Backoffice est accessible sur `http://localhost:5000`. Les identifiants de
l'administrateur initial proviennent de `SEED_ADMIN_USERNAME` et
`SEED_ADMIN_PASSWORD` dans le fichier `.env` non suivi.

## Usage du client web

Le client est accessible sur `http://localhost:8080`. Il envoie les questions
à `POST http://localhost:8001/api/query`. Les réponses de stock par branche
listent les identifiants Produit et leurs quantités. Les erreurs HTTP prévues
affichent uniquement le message public structuré retourné par le service IA.

## Tests Backoffice reproductibles

Cette commande crée un PostgreSQL 16 éphémère nommé exclusivement
`hbntory_test`, attend son healthcheck, applique les migrations puis exécute
la suite complète :

```bash
docker compose -f docker-compose.test.yml \
  up --build --abort-on-container-exit \
  --exit-code-from backoffice-tests
```

Elle n'utilise ni le volume ni les identifiants de la base principale. Après
l'exécution, les conteneurs de test peuvent être retirés sans option de volume :

```bash
docker compose -f docker-compose.test.yml down
```

Le retrait de stock est réalisé par une décrémentation SQL conditionnelle
atomique. PostgreSQL accepte le retrait uniquement si la quantité disponible
est encore suffisante au moment de l'`UPDATE`.

Les autres suites se lancent dans leur dossier :

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  -m pytest -v -p no:cacheprovider
```

Le client est contrôlé sans chaîne frontend supplémentaire :

```bash
node --check client_web/script.js
node --check client_web/background.js
```

## Reconstruction Docker

Les images de production installent uniquement `requirements.txt` :

```bash
docker compose config --quiet
docker compose build backoffice product-mcp-server
docker compose build
```

## Décisions techniques

Voir les décisions acceptées dans [docs/adr/](docs/adr/).

## Limitations connues

Le modèle Ollama doit être téléchargé une première fois avec
`docker compose exec ollama ollama pull gemma3:latest`. Le mode `hybrid`
continue à répondre avec les règles et `AnswerBuilder` si un fournisseur IA
est indisponible.
