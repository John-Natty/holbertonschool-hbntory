# ADR 0002 — Utiliser le rendu côté serveur pour le Backoffice

## Statut

Accepté

## Contexte

Le Backoffice doit permettre aux utilisateurs authentifiés de gérer les
utilisateurs et les stocks selon leur rôle.

L’interface doit notamment proposer :

- un formulaire de connexion ;
- une liste des utilisateurs ;
- des formulaires de création et de modification des utilisateurs ;
- la désactivation et la réactivation des utilisateurs ;
- l’affectation des utilisateurs à une branche ;
- la consultation du stock d’une branche ;
- l’ajout et le retrait de stock.

Deux approches principales ont été envisagées :

- une API REST avec une application frontend indépendante en HTML, CSS et
  JavaScript ;
- un rendu côté serveur avec Flask et Jinja2, complété par du JavaScript pour
  certaines interactions.

Le projet doit être réalisé en équipe dans un délai limité. La priorité est de
fournir une interface simple, fonctionnelle, sécurisée et conforme aux règles
d’autorisation.

## Décision

Nous utilisons Flask et Jinja2 pour générer les pages principales du
Backoffice côté serveur.

Flask est responsable :

- du routage ;
- de l’authentification ;
- de la gestion des sessions ;
- de la validation des formulaires ;
- de la protection CSRF ;
- des contrôles de rôle et de branche ;
- de l’accès à PostgreSQL avec SQLAlchemy ;
- du rendu des templates Jinja2.

Le Backoffice n’est toutefois pas exclusivement fondé sur le rechargement
complet des pages.

Du JavaScript est utilisé pour améliorer l’expérience utilisateur, notamment
pour les mouvements de stock. L’interface peut envoyer une requête à une route
JSON contrôlée par Flask, puis mettre à jour l’affichage sans recharger
entièrement la page.

Le flux principal reste sous le contrôle du backend :

```text
Navigateur authentifié
→ route Flask
→ authentification et autorisation
→ validation des données
→ service métier
→ SQLAlchemy
→ PostgreSQL
```

Pour les mouvements de stock réalisés avec JavaScript :

```text
Page rendue par Flask et Jinja2
→ requête JavaScript vers une route Flask JSON
→ validation CSRF
→ contrôle du rôle et de la branche
→ modification du stock
→ réponse JSON
→ mise à jour de l’interface
```

Le JavaScript ne contourne jamais les règles du backend et n’accède jamais
directement à PostgreSQL.

## Raisons du choix

Cette approche hybride a été retenue car :

- le Backoffice est principalement composé de formulaires et de listes ;
- Flask et Jinja2 permettent de développer rapidement les pages principales ;
- le rendu serveur s’intègre naturellement avec l’authentification par session ;
- les contrôles de rôle et de branche restent centralisés dans Flask ;
- la validation des données ne dépend pas du navigateur ;
- JavaScript peut améliorer les interactions fréquentes sans nécessiter une
  application frontend entièrement séparée ;
- l’équipe n’a pas besoin de maintenir une API REST complète pour toutes les
  fonctionnalités du Backoffice ;
- cette solution offre un bon compromis entre simplicité, sécurité et confort
  d’utilisation.

## Conséquences

### Conséquences positives

- L’architecture du Backoffice reste simple à comprendre.
- L’authentification par session s’intègre directement avec Flask-Login.
- Les pages principales sont générées avec Jinja2.
- Les formulaires peuvent être validés côté serveur.
- Les règles d’autorisation restent centralisées dans le backend.
- Les common users sont limités à leur branche par le serveur.
- L’administrateur ne peut pas effectuer d’opérations de stock.
- La protection CSRF est appliquée aux opérations sensibles.
- Les mouvements de stock peuvent être effectués sans rechargement complet de
  la page.
- Une erreur JavaScript ne permet pas de contourner les contrôles métier du
  backend.

### Conséquences négatives

- Le frontend reste fortement lié aux routes et aux templates Flask.
- Certaines fonctionnalités dépendent de JavaScript pour offrir leur
  expérience principale.
- Deux formats de réponse doivent être maintenus :
  - des pages HTML ;
  - certaines réponses JSON.
- La réutilisation du Backoffice par une autre application est limitée.
- Une évolution vers une application frontend totalement indépendante
  nécessiterait de créer et de documenter une API dédiée.
- Les interactions JavaScript doivent conserver la gestion des erreurs, de la
  sécurité CSRF et des états de chargement.

## Alternatives rejetées

### Application frontend indépendante avec API REST complète

Cette solution aurait consisté à séparer entièrement :

- le backend Flask ;
- une API JSON ;
- une application frontend autonome.

Elle n’a pas été retenue car :

- elle aurait augmenté le nombre de routes et de contrats à maintenir ;
- elle aurait demandé davantage de JavaScript ;
- elle aurait complexifié l’authentification et la protection CSRF ;
- elle n’était pas nécessaire pour satisfaire le périmètre du MVP ;
- elle aurait augmenté le temps d’intégration pour une équipe de taille
  limitée.

### Rendu serveur sans JavaScript

Cette solution aurait reposé uniquement sur des formulaires HTML et des
rechargements complets de pages.

Elle n’a pas été retenue pour toutes les fonctionnalités car les mouvements de
stock sont plus agréables à utiliser avec une interaction JavaScript et une
réponse JSON immédiate.

## Limites

Le Backoffice reste principalement une application Flask rendue côté serveur,
mais il ne doit plus être décrit comme une application exclusivement SSR.

L’interface de gestion des stocks utilise JavaScript pour certaines opérations,
tout en conservant Flask comme autorité unique pour :

- l’authentification ;
- les autorisations ;
- la validation ;
- les transactions ;
- l’accès à la base de données.
