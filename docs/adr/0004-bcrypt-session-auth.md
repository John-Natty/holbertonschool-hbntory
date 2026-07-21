# ADR 0004 — Utiliser bcrypt et des sessions Flask pour l’authentification

## Statut

Accepté

## Contexte

Le Backoffice est réservé aux utilisateurs internes authentifiés.

Le système doit :

- vérifier les identifiants de connexion ;
- empêcher les utilisateurs désactivés de se connecter ;
- protéger les routes privées ;
- distinguer les rôles `admin` et `common` ;
- empêcher un common user d’agir sur une autre branche ;
- empêcher l’administrateur de gérer le stock ;
- stocker les mots de passe de manière sécurisée.

Deux mécanismes d’authentification ont principalement été envisagés :

- une authentification basée sur des sessions ;
- une authentification basée sur des tokens, par exemple JWT.

Le Backoffice utilise un rendu côté serveur avec Flask et Jinja2. Il est
utilisé depuis un navigateur et ne doit pas être consommé par une
application mobile ou plusieurs frontends indépendants dans le MVP.

Pour les mots de passe, un simple stockage en clair ou un simple hachage
SHA-256 ne serait pas suffisamment sécurisé.

## Décision

Nous avons choisi :

- bcrypt pour le hachage des mots de passe ;
- des sessions Flask pour maintenir l’utilisateur authentifié ;
- Flask-Login pour gérer la connexion, la déconnexion et l’utilisateur
  courant.

Les mots de passe ne seront jamais enregistrés en clair dans PostgreSQL.

Seul leur hash bcrypt sera conservé dans la colonne `password_hash`.

Après une connexion réussie, une session sera créée dans le navigateur.
Les routes protégées vérifieront l’utilisateur connecté avant d’exécuter
une opération.

## Flux d’authentification

Le processus de connexion sera le suivant :

1. L’utilisateur envoie son identifiant et son mot de passe.
2. Le Backoffice recherche l’utilisateur dans PostgreSQL.
3. Le système vérifie que le compte existe.
4. Le système vérifie que le compte est actif.
5. bcrypt compare le mot de passe fourni avec le hash enregistré.
6. Si les informations sont valides, une session est créée.
7. L’utilisateur est redirigé vers l’espace correspondant à son rôle.

Un utilisateur désactivé avec un soft-delete ne pourra pas ouvrir de
nouvelle session.

## Autorisation

L’authentification indique qui est connecté.

L’autorisation détermine ce que cet utilisateur peut faire.

Les règles seront contrôlées côté backend :

- un common user peut gérer uniquement le stock de sa branche ;
- un common user ne peut pas gérer les utilisateurs ;
- l’administrateur peut gérer les common users ;
- l’administrateur ne peut pas effectuer d’opération de stock ;
- un utilisateur anonyme ne peut pas accéder au Backoffice.

Le fait de cacher un bouton dans l’interface ne sera jamais considéré
comme une mesure de sécurité suffisante.

## Raisons du choix

bcrypt a été retenu car :

- il est conçu pour le stockage des mots de passe ;
- il applique automatiquement un sel ;
- il est volontairement coûteux en calcul ;
- il réduit l’efficacité des attaques par force brute ;
- il permet de vérifier un mot de passe sans le déchiffrer.

Les sessions Flask ont été retenues car :

- le Backoffice est une application web rendue côté serveur ;
- elles s’intègrent naturellement avec Flask et Jinja2 ;
- elles simplifient la connexion et la déconnexion ;
- aucun token ne doit être géré manuellement dans le frontend ;
- Flask-Login facilite la protection des routes et l’accès à l’utilisateur
  courant.

## Pourquoi SHA-256 seul n’est pas suffisant

SHA-256 est un algorithme de hachage généraliste très rapide.

Cette rapidité permet à un attaquant de tester un grand nombre de mots de
passe en peu de temps.

bcrypt est volontairement plus lent et utilise un sel, ce qui le rend
plus adapté au stockage sécurisé des mots de passe.

## Configuration de sécurité

La configuration reposera sur des variables d’environnement.

Le projet devra notamment utiliser :

- une `SECRET_KEY` non publiée ;
- un cookie de session `HttpOnly` ;
- une politique `SameSite` adaptée ;
- une déconnexion supprimant la session active ;
- un fichier `.env` ignoré par Git ;
- un fichier `.env.example` ne contenant aucun véritable secret.

## Conséquences

### Conséquences positives

- Les mots de passe ne sont jamais stockés en clair.
- La connexion et la déconnexion sont simples à gérer.
- Les routes privées peuvent être protégées avec Flask-Login.
- Le système est adapté au rendu côté serveur.
- Les rôles et les branches peuvent être vérifiés à chaque requête.
- Les utilisateurs soft-deleted peuvent être refusés lors de la connexion.

### Conséquences négatives

- bcrypt ajoute volontairement un coût de calcul lors de la vérification
  des mots de passe.
- Les sessions sont moins adaptées à plusieurs clients indépendants ou à
  une application mobile.
- La configuration de la `SECRET_KEY` et des cookies doit être correctement
  protégée.
- Une évolution future vers une API publique pourrait nécessiter une autre
  stratégie d’authentification.