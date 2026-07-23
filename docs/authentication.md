# Authentification et sécurité du Backoffice

## Présentation

Le Backoffice de HBntory est réservé aux utilisateurs authentifiés.

Deux rôles sont disponibles :

- `admin` ;
- `common`.

L’authentification repose sur des sessions Flask avec Flask-Login.

Les mots de passe sont protégés avec bcrypt grâce à Flask-Bcrypt.

Aucun mot de passe en clair n’est enregistré dans la base de données.

---

## Mécanisme de hachage utilisé

HBntory utilise `bcrypt` pour protéger les mots de passe des utilisateurs.

Bcrypt est un algorithme spécialement conçu pour le stockage sécurisé des
mots de passe.

Dans le projet, Flask-Bcrypt est initialisé une seule fois dans le fichier
`app/extensions.py` :

```python
from flask_bcrypt import Bcrypt

bcrypt = Bcrypt()
```

Cette même instance est ensuite utilisée dans toute l’application.

---

## Stockage des mots de passe

La table `users` ne possède aucun champ contenant le mot de passe en clair.

Elle contient uniquement la colonne :

```text
password_hash
```

Lorsqu’un utilisateur choisit un mot de passe, celui-ci est transformé en
hash avant son enregistrement dans PostgreSQL.

Le modèle `User` utilise la méthode suivante :

```python
def set_password(self, password):
    """Enregistre le mot de passe sous forme de hash bcrypt."""
    if not isinstance(password, str) or not password.strip():
        raise ValueError("Le mot de passe ne peut pas être vide.")

    self.password_hash = bcrypt.generate_password_hash(
        password
    ).decode("utf-8")
```

Cette méthode réalise plusieurs opérations :

1. elle vérifie que la valeur reçue est une chaîne de caractères ;
2. elle refuse un mot de passe vide ;
3. elle génère un hash bcrypt ;
4. elle enregistre uniquement le hash dans `password_hash`.

Le mot de passe original n’est jamais conservé.

---

## Utilisation d’un sel

Bcrypt génère automatiquement un sel aléatoire lors de chaque hachage.

Le sel permet d’obtenir des résultats différents, même lorsque deux
utilisateurs choisissent le même mot de passe.

Par exemple, deux utilisateurs utilisant :

```text
MonMotDePasse123
```

peuvent obtenir deux hashs différents.

Cela rend les attaques utilisant des tables de hashs précalculés beaucoup
plus difficiles.

---

## Vérification du mot de passe

Lors de la connexion, le mot de passe fourni par l’utilisateur n’est pas
haché puis comparé manuellement.

La méthode `check_password()` demande directement à bcrypt de comparer le
mot de passe reçu avec le hash stocké :

```python
def check_password(self, password):
    """Vérifie un mot de passe par rapport au hash enregistré."""
    return bcrypt.check_password_hash(
        self.password_hash,
        password,
    )
```

La méthode retourne :

```text
True
```

si le mot de passe correspond au hash enregistré.

Elle retourne :

```text
False
```

si le mot de passe est incorrect.

Le mot de passe original ne peut pas être récupéré depuis le hash.

---

## Pourquoi SHA-256 seul n’est pas suffisant

SHA-256 est une fonction de hachage générale.

Elle est conçue pour produire rapidement une empreinte à partir de données.

Cette rapidité est utile pour vérifier l’intégrité d’un fichier, mais elle
est dangereuse pour le stockage des mots de passe.

Un attaquant peut tester un très grand nombre de mots de passe en peu de
temps avec SHA-256.

Utiliser uniquement SHA-256 ne fournit pas automatiquement :

- un sel aléatoire propre à chaque mot de passe ;
- un facteur de coût configurable ;
- un ralentissement volontaire du calcul ;
- une protection adaptée contre les attaques par force brute.

Bcrypt est volontairement plus lent.

Son facteur de coût permet également d’augmenter progressivement la
difficulté du calcul lorsque les ordinateurs deviennent plus puissants.

---

## Authentification par session

HBntory utilise une authentification basée sur les sessions Flask.

Lorsqu’un utilisateur fournit des identifiants valides :

1. le Backoffice recherche son compte ;
2. il vérifie que le compte est actif ;
3. il vérifie le mot de passe avec bcrypt ;
4. Flask-Login enregistre l’utilisateur dans la session ;
5. l’utilisateur peut accéder aux routes protégées.

Ce choix est adapté au Backoffice, car il s’agit d’une application Flask
avec un rendu côté serveur grâce à Jinja2.

Une authentification par token n’est pas nécessaire pour le MVP.

---

## Comptes désactivés

Le soft-delete est géré avec le champ :

```text
is_active
```

Un utilisateur désactivé reste présent dans PostgreSQL, mais il ne peut
plus se connecter.

Le compte est désactivé en définissant :

```text
is_active = false
```

Cela permet de conserver les données liées à l’utilisateur sans supprimer
définitivement son compte.

---

## Autorisations par rôle

Deux rôles existent dans le Backoffice.

### Administrateur

L’administrateur peut :

- lister les common users ;
- créer un common user ;
- assigner une branche ;
- modifier la branche d’un common user ;
- changer son mot de passe ;
- désactiver son compte.

L’administrateur ne peut pas gérer les stocks.

### Common user

Un common user appartient obligatoirement à une branche.

Il peut uniquement :

- consulter le stock de sa branche ;
- ajouter du stock dans sa branche ;
- retirer du stock dans sa branche.

Il ne peut pas gérer les utilisateurs ni agir sur une autre branche.

---

## Contrôle côté backend

Les autorisations ne reposent jamais uniquement sur l’affichage de
l’interface.

Cacher un bouton dans une page HTML ne protège pas une route.

Chaque requête protégée doit vérifier côté backend :

- que l’utilisateur est authentifié ;
- que son compte est actif ;
- que son rôle autorise l’action ;
- que sa branche correspond à la ressource utilisée.

Une requête interdite doit être refusée même si elle est envoyée
manuellement sans utiliser l’interface.

---

## Règles de sécurité

HBntory applique les règles suivantes :

- aucun mot de passe en clair n’est stocké ;
- seul `password_hash` est enregistré ;
- bcrypt est utilisé pour créer et vérifier les hashs ;
- les mots de passe vides sont refusés ;
- le hash n’apparaît pas dans `__repr__` ;
- le hash ne doit jamais être envoyé dans une réponse HTTP ;
- le hash ne doit jamais être affiché dans une page HTML ;
- un utilisateur désactivé ne peut pas se connecter ;
- les routes du Backoffice sont protégées ;
- les rôles sont vérifiés côté backend ;
- un common user ne peut agir que sur sa branche ;
- l’administrateur ne peut pas gérer le stock.

---

## Utilisation commune du hachage

Les méthodes du modèle `User` doivent être utilisées partout dans le
Backoffice :

```python
user.set_password(password)
user.check_password(password)
```

Elles seront utilisées pour :

- créer l’administrateur initial dans `seed.py` ;
- créer un common user ;
- modifier le mot de passe d’un utilisateur ;
- vérifier les identifiants pendant la connexion.

Cette organisation garantit que toutes les parties de l’application
utilisent le même mécanisme de sécurité.