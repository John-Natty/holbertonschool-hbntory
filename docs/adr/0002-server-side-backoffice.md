# ADR 0002 — Utiliser le rendu côté serveur pour le Backoffice

## Statut

Accepté

## Contexte

Le Backoffice doit permettre aux utilisateurs authentifiés de gérer
les utilisateurs et les stocks selon leur rôle.

L’interface doit principalement proposer :

- un formulaire de connexion ;
- des listes d’utilisateurs ;
- des formulaires de création et de modification ;
- des listes de stocks ;
- des formulaires d’ajout et de retrait de stock.

Deux approches ont été envisagées :

- une API REST avec une interface HTML, CSS et JavaScript séparée ;
- un rendu côté serveur avec Flask et Jinja2.

Le projet doit être réalisé en équipe dans un délai limité. La priorité
est de fournir une interface simple, fonctionnelle et sécurisée.

## Décision

Nous avons choisi d’utiliser un rendu côté serveur avec Flask et Jinja2
pour le Backoffice.

Flask traitera les requêtes, vérifiera l’authentification et les
autorisations, interrogera la base de données avec SQLAlchemy, puis
générera les pages HTML à partir de templates Jinja2.

Du JavaScript pourra être utilisé pour des améliorations mineures, mais
le fonctionnement principal du Backoffice ne devra pas en dépendre.

## Raisons du choix

Le rendu côté serveur a été retenu car :

- le Backoffice est principalement composé de formulaires et de listes ;
- cette approche nécessite peu de JavaScript ;
- elle s’intègre naturellement avec l’authentification par session ;
- les contrôles de rôle et de branche restent centralisés dans le backend ;
- elle permet de développer rapidement une interface fonctionnelle ;
- elle réduit la complexité du projet pour une équipe de deux personnes.

## Conséquences

### Conséquences positives

- Le développement du Backoffice est plus simple et plus rapide.
- L’authentification par session s’intègre facilement.
- Les formulaires peuvent être validés directement côté serveur.
- Les règles d’autorisation restent centralisées dans Flask.
- Moins de routes API JSON et de code JavaScript sont nécessaires.

### Conséquences négatives

- Le frontend est davantage lié au backend Flask.
- Les pages complètes sont généralement rechargées après une action.
- L’interface est moins facilement réutilisable par une autre application.
- Une évolution future vers une application frontend indépendante
  demanderait la création d’une API dédiée.