# ADR 0003 — Utiliser notre propre serveur MCP pour l’accès aux stocks

## Statut

Accepté

## Contexte

Le service AI Query doit pouvoir accéder à deux catégories de données :

- les informations produit provenant de l’API Produit externe ;
- les informations de stock enregistrées dans la base de données locale.

Plusieurs solutions ont été envisagées pour fournir les stocks à l’agent IA :

- étendre notre propre serveur MCP avec des outils de stock ;
- utiliser un MCP de base de données tiers ;
- permettre au service IA d’accéder directement à la base de données.

L’accès direct à PostgreSQL par l’agent présenterait des risques de
sécurité et créerait un couplage important entre le service IA et la
structure interne de la base de données.

## Décision

Nous avons choisi d’étendre notre propre serveur MCP avec des outils
de consultation des stocks.

Le serveur MCP exposera des opérations contrôlées permettant notamment de :

- consulter les branches ayant un produit en stock ;
- consulter les produits disponibles dans une branche ;
- vérifier si une liste d’achats peut être satisfaite par une ou plusieurs
  branches.

Le serveur MCP n’accédera pas directement à PostgreSQL.

Pour récupérer les stocks, il utilisera une API interne en lecture seule
exposée par le Backoffice.

L’agent IA ne pourra pas exécuter de requêtes SQL libres.

## Outils prévus

Les outils de stock pourront inclure :

- `get_stock_by_product(product_id)` ;
- `get_stock_by_branch(branch_id)` ;
- `check_shopping_list(items)`.

Les outils produits resteront également disponibles :

- `list_products()` ;
- `get_product_details(product_id)`.

## Raisons du choix

Notre propre MCP a été retenu car :

- les opérations disponibles pour l’agent sont précisément contrôlées ;
- l’agent ne dispose d’aucun accès direct à PostgreSQL ;
- aucune requête SQL libre ne peut être générée ;
- les outils sont simples à tester séparément ;
- la gestion des erreurs peut être centralisée ;
- cette solution respecte les frontières entre les services ;
- elle est plus simple à maîtriser qu’un MCP de base de données tiers.

## Conséquences

### Conséquences positives

- L’accès aux stocks est limité à des opérations autorisées.
- La structure interne de la base de données n’est pas exposée à l’agent.
- Les outils MCP peuvent être testés indépendamment du service IA.
- Les réponses de l’agent reposent sur des données contrôlées.
- Le Backoffice reste responsable de l’accès à PostgreSQL.
- Les erreurs peuvent être retournées sous une forme claire et structurée.

### Conséquences négatives

- Chaque nouveau type de requête peut nécessiter la création d’un nouvel outil.
- Une API interne supplémentaire doit être développée dans le Backoffice.
- Le service MCP dépend de la disponibilité du Backoffice pour consulter
  les stocks.
- Cette solution demande davantage de développement qu’un accès direct à
  la base de données.