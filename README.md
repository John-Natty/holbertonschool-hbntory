# HBntory

## Overview

HBntory est une plateforme d'inventaire multi-branches composée d'un
Backoffice Flask authentifié, d'un serveur MCP en lecture seule, d'un service
IA FastAPI et d'un client web public.

Le public interroge un assistant conversationnel pour connaître le catalogue
et la disponibilité des produits. Les employés gèrent le stock de leur propre
branche depuis le Backoffice. Les administrateurs gèrent les comptes.

## Résumé de l'architecture

Le client interroge uniquement le service IA. L'IA utilise uniquement les cinq
outils du serveur MCP. Le MCP lit les produits depuis l'API Produit officielle
et les stocks depuis l'API interne protégée du Backoffice. Seul le Backoffice
accède à PostgreSQL.

Voir [docs/architecture.md](docs/architecture.md) pour les diagrammes, les
contrats et les règles de propriété des données.

## Services et ports

| Service | Rôle | Adresse locale |
|---|---|---|
| `client-web` | Site public, assistant et catalogue | `http://localhost:8080` |
| `ai-service` | Compréhension des questions, orchestration | `http://localhost:8001` |
| `product-mcp-server` | Cinq outils de lecture exposés à l'IA | `http://localhost:8000` |
| `backoffice` | Authentification, stock, comptes | `http://localhost:5000` |
| `external-products-api` | Catalogue officiel fourni par l'école | `http://localhost:5001` |
| `database` | PostgreSQL, propriété du Backoffice | `localhost:5432` |

Les ports publiés sont configurables : `CLIENT_WEB_HOST_PORT`,
`AI_SERVICE_HOST_PORT`, `PRODUCT_API_PORT` et `POSTGRES_PORT`.

## Structure du dépôt

```
client_web/            Site public : assistant, catalogue en cartes, images
ai_service/            Service IA FastAPI, classifieur, orchestrateur
product_mcp_server/    Serveur MCP, cinq outils de lecture
backoffice/            Flask : authentification, stock, administration
docs/                  Architecture, authentification, MVP et ADR
```

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

La même commande s'applique à `product_mcp_server` et à `ai_service`, chacun
possédant ses fichiers `requirements.txt` et `requirements-dev.txt` séparés.

## Lancement des services

Le mode Compose par défaut démarre PostgreSQL, l'API Produit, le Backoffice,
le serveur MCP, le service IA et le client web :

```bash
cp .env.example .env
# Remplacer les valeurs d'exemple sensibles.

docker compose up -d
docker compose ps
```

Le fournisseur principal est MiniMax-M3 via l'API NVIDIA. Renseigner
`NVIDIA_API_KEY` active ses deux usages bornés : classification et rédaction.
Sans clé ou si NVIDIA est indisponible, le service démarre normalement avec
les règles Python et `AnswerBuilder`. Aucun modèle local n'est démarré.

Vérifier que la clé est bien prise en compte :

```bash
curl -s http://localhost:8001/ready
```

La réponse doit indiquer `"active_provider":"nvidia"`. Si elle indique
`"rules"`, la clé n'a pas été lue et l'assistant fonctionne en mode dégradé.

### Réglage `AI_NATURAL_ANSWERS`

Le service peut appeler le modèle deux fois par question : une fois pour
comprendre la demande, une fois pour rédiger la phrase de réponse. La seconde
passe est validée fait par fait, et rejetée dès qu'un chiffre ou un nom ne
correspond pas exactement aux données.

`AI_NATURAL_ANSWERS=false` désactive uniquement cette rédaction. La
compréhension reste entière et les réponses proviennent du générateur
déterministe. Le temps de réponse est divisé par environ cinq. La valeur par
défaut est `true`.

## Initialisation de la base de données

Le Backoffice applique automatiquement les migrations au démarrage. Après son
healthcheck, le seed initial peut être exécuté plusieurs fois sans doublon :

```bash
docker compose exec backoffice python seed.py
```

Le seed crée les deux branches configurées et au plus un administrateur.

## Le client web public

Accessible sur `http://localhost:8080`, sans authentification.

Le cadre jaune de l'assistant reste collé en haut de la fenêtre : le catalogue
défile derrière lui, ce qui permet de poser une question depuis n'importe quel
endroit de la liste. Sous ce cadre, les 39 produits sont présentés en cartes
avec leur nom, leur prix et une illustration.

Un clic sur une carte pré-remplit la question correspondante sans jamais
l'envoyer : l'utilisateur reste seul décisionnaire.

Le bouton **Espace équipe** mène à la connexion du Backoffice.

Le client appelle deux routes du service IA :

| Route | Usage |
|---|---|
| `GET /api/products` | Charge le catalogue affiché en cartes |
| `POST /api/query` | Envoie une question de l'utilisateur |

Les erreurs HTTP prévues affichent uniquement le message public structuré
retourné par le service IA.

## Ce que l'assistant comprend

Les questions sont posées en langage libre. L'assistant reconnaît un produit
de deux façons.

**Par son numéro**, par exemple « stock du produit 12 » ou « combien coûte le
produit 3 ? ».

**Par son nom**, par exemple « où est la chaise ergonomique ? » ou « prix de
la webcam ». Un mot ne désigne un produit que s'il n'en désigne qu'un seul
dans tout le catalogue. « ergonomic » identifie la chaise ; « monitor » n'en
identifie aucun puisque deux écrans le portent, et l'assistant demande alors
de préciser plutôt que de choisir.

Cette reconnaissance est déterministe et ne consulte pas le modèle : la
réponse est immédiate et ne peut pas être inventée.

L'assistant refuse les questions hors périmètre et toute demande d'écriture.
Il est strictement en lecture seule.

## Le Backoffice

Accessible sur `http://localhost:5000`. Les identifiants de l'administrateur
initial proviennent de `SEED_ADMIN_USERNAME` et `SEED_ADMIN_PASSWORD` dans le
fichier `.env` non suivi.

La page d'accueil s'adapte au rôle du compte connecté :

| Rôle | Page d'arrivée | Droits |
|---|---|---|
| `admin` | Gestion des utilisateurs | Comptes et branches, jamais le stock |
| `common` | Catalogue de sa branche | Stock de sa seule branche |

### Gestion du stock

L'employé voit le catalogue de sa branche en cartes, quatre par ligne. Les
produits qu'il détient figurent en haut, les autres en dessous en
transparence. Chaque carte affiche la quantité, un bouton vert pour ajouter et
un bouton rouge pour retirer.

Un appui maintenu fait défiler les quantités : la répétition démarre après
400 millisecondes, puis accélère. Le chiffre change immédiatement à l'écran,
et le serveur n'est prévenu qu'au relâchement, en une seule requête portant le
total du mouvement.

Le retrait de stock est réalisé par une décrémentation SQL conditionnelle
atomique. PostgreSQL accepte le retrait uniquement si la quantité disponible
est encore suffisante au moment de l'`UPDATE`.

### Routes principales

| Route | Méthode | Usage |
|---|---|---|
| `/` | GET | Accueil adapté au rôle |
| `/auth/entree` | GET | Entrée publique, ferme toute session en cours |
| `/auth/login` | GET, POST | Formulaire de connexion |
| `/auth/logout` | POST | Déconnexion |
| `/admin/users` | GET | Liste des comptes, réservée à l'admin |
| `/branches/<id>/stock` | GET | Catalogue de la branche |
| `/branches/<id>/stock/move` | POST | Mouvement de stock en JSON |

`/auth/entree` existe pour les postes partagés en branche : elle ferme la
session ouverte avant d'afficher le formulaire, afin que l'employé suivant
n'hérite jamais de la session du précédent.

Voir [docs/authentication.md](docs/authentication.md) pour les rôles, les
sessions et les protections.

## Les illustrations produits

Les images sont stockées dans `client_web/img/`, et dupliquées dans
`backoffice/app/static/img/` puisque les deux services sont des conteneurs
distincts.

```
img/products/<id>.webp        Une image par produit
img/categories/<slug>.webp    Repli par famille de produits
```

L'API Produit ne fournit aucune image : elles sont fabriquées à part, au
format paysage 302 sur 173 pixels. Une carte cherche d'abord l'image de son
produit, puis celle de sa catégorie, puis une image générique. Aucune carte ne
peut donc se retrouver sans illustration.

La correspondance est déclarée en haut de `client_web/script.js` : une ligne
par catégorie, et l'ensemble des identifiants disposant d'une image propre.

## Tests

Chaque service possède sa suite.

| Suite | Tests |
|---|---|
| `ai_service` | 395 |
| `product_mcp_server` | 142 |
| `backoffice` | 117 |

### Backoffice, de façon reproductible

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

### Les autres suites

Elles se lancent depuis leur dossier :

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  -m pytest -v -p no:cacheprovider
```

Lancer la suite du Backoffice depuis l'hôte plutôt que par Docker demande
d'exporter quatre variables à la main, le fichier `.env` n'étant pas chargé
automatiquement :

```bash
TEST_DATABASE_URL, SECRET_KEY, INTERNAL_API_KEY,
PRODUCT_API_BASE_URL=http://localhost:5001
```

Sans la dernière, un test échoue alors que le code est correct : la
configuration de test force une adresse volontairement injoignable, et ce test
a besoin de l'API Produit réelle.

### Le client web

Il est contrôlé sans chaîne frontend supplémentaire :

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

Les fichiers statiques du client et du Backoffice sont copiés dans les images :
toute modification du HTML, du CSS, du JavaScript ou des images demande un
`docker compose up -d --build`, sans quoi l'ancienne version reste servie.

## Décisions techniques

Voir les décisions acceptées dans [docs/adr/](docs/adr/).

## Limitations connues

Le mode `nvidia` dépend d'Internet, d'une clé NVIDIA valide, des quotas du
fournisseur et de la disponibilité du modèle `minimaxai/minimax-m3`.
L'absence de clé ou une erreur fournisseur active `rules` et
`AnswerBuilder`.

Les questions résolues par le modèle prennent plusieurs secondes, parfois
davantage, le modèle produisant un raisonnement avant de répondre. Les
questions reconnues par leur nom de produit ou par leur numéro dans une
formulation connue sont, elles, immédiates.

Les conversations restent volatiles et locales à une seule instance du service
IA. Les références d'un tour à l'autre ne sont résolues que pour un ensemble
borné de formulations.

Un produit dont l'API Produit signale l'arrêt n'apparaît pas dans le
catalogue. S'il restait du stock d'un tel produit dans une branche, il ne
serait pas affiché.
