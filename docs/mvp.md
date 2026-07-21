# MVP — HBntory

Ce document définit le périmètre. La **partie 1** est le scope **obligatoire** :
on la termine avant toute autre chose. La **partie 2** liste ce qui est
**optionnel**, à ne considérer que s'il reste du temps.

## Partie 1 — MVP (scope obligatoire, à faire en premier)

### Backoffice

- Connexion et déconnexion.
- Gestion des *common users* par l'admin.
- Attribution d'une branche à un utilisateur.
- Soft-delete des utilisateurs.
- Consultation du stock.
- Ajout de stock.
- Retrait de stock.
- Contrôle des rôles côté backend.
- Docker Compose global.
- Suite de tests automatisés.

### Serveur MCP

- Lister les produits.
- Obtenir le détail d'un produit.
- Consulter le stock par produit.
- Consulter le stock par branche.
- Vérifier une liste d'achats.

### Service IA

- Donner les détails d'un produit.
- Indiquer les branches possédant un produit.
- Lister les produits disponibles dans une branche.
- Indiquer quelle branche peut satisfaire une liste d'achats.

### Client public

- Champ de question.
- Bouton d'envoi.
- Indicateur de chargement.
- Affichage de la réponse.
- Gestion des erreurs.

## Partie 2 — Plus tard / optionnel (seulement si le temps le permet)

Ces éléments correspondent aux **stretch goals de la Task 9** et ne sont abordés
que si le scope obligatoire est **entièrement terminé** :

- Historique de stock.
- Journaux d'audit (audit logs).
- Mémoire de conversation.
- Streaming SSE / WebSocket.
- Documentation OpenAPI.
- Rate limiting.
- Meilleure recherche produit.
- Styling de l'interface.
- Déploiement cloud.

> **Règle :** une option de la partie 2 ne compense **jamais** un élément
> obligatoire de la partie 1 laissé incomplet. Le scope obligatoire passe
> toujours avant.