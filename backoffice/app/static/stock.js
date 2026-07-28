"use strict";

// Boutons + et - des cartes produit : le chiffre bouge tout de suite à
// l'écran, le serveur n'est prévenu qu'au relâchement du bouton, en une
// seule requête portant le total du mouvement.
(function () {
    const catalogue = document.getElementById("catalog");

    if (!catalogue) {
        return;
    }

    // Cadence de la répétition pendant un appui maintenu. Valeurs reprises
    // de la répétition des touches du clavier : un délai avant de démarrer
    // pour ne pas se déclencher sur un clic un peu lent, puis une
    // accélération pour les gros mouvements.
    const DELAI_AVANT_REPETITION = 400;
    const CADENCE_NORMALE = 150;
    const CADENCE_RAPIDE = 60;
    const PAS_AVANT_ACCELERATION = 10;

    const URL_MOUVEMENT = catalogue.dataset.moveUrl;
    const JETON_CSRF = catalogue.dataset.csrfToken;

    const grillePresents = document.getElementById("stock-present");
    const grilleAbsents = document.getElementById("stock-absent");

    // Appui en cours : minuteur, sens du pas et carte concernée.
    let appui = null;


    // Retourne la quantité actuellement affichée sur une carte.
    function quantiteAffichee(carte) {
        return Number(
            carte.querySelector(".product-card-qty-value").textContent.trim()
        );
    }


    // Écrit une quantité sur une carte.
    function afficheQuantite(carte, quantite) {
        carte.querySelector(
            ".product-card-qty-value"
        ).textContent = String(quantite);
    }


    // Retourne la dernière quantité confirmée par le serveur.
    function quantiteConfirmee(carte) {
        if (carte.dataset.confirmed === undefined) {
            carte.dataset.confirmed = String(quantiteAffichee(carte));
        }

        return Number(carte.dataset.confirmed);
    }


    // Affiche un message d'erreur au-dessus du contenu, puis l'efface.
    function signale(message) {
        const zone = document.querySelector("main");
        const bloc = document.createElement("div");

        bloc.className = "message danger";
        bloc.textContent = message;
        zone.insertBefore(bloc, zone.firstChild);

        window.setTimeout(function () {
            bloc.remove();
        }, 6000);
    }


    // Fait clignoter la carte dans la couleur du mouvement.
    function pulse(carte, sens) {
        const classe = sens > 0 ? "is-added" : "is-removed";

        carte.classList.remove("is-added", "is-removed");

        // Force le navigateur à rejouer l'animation.
        void carte.offsetWidth;

        carte.classList.add(classe);
    }


    // Insère une carte dans une grille en respectant l'ordre alphabétique.
    function insereTriee(grille, carte) {
        const nom = carte.querySelector(
            ".product-card-name"
        ).textContent.trim().toLowerCase();

        const voisines = grille.querySelectorAll(".product-card");

        for (const voisine of voisines) {
            const autre = voisine.querySelector(
                ".product-card-name"
            ).textContent.trim().toLowerCase();

            if (nom < autre) {
                grille.insertBefore(carte, voisine);
                return;
            }
        }

        grille.appendChild(carte);
    }


    // Met à jour les compteurs et les messages « aucun produit ».
    function rafraichitCompteurs() {
        const groupes = [
            ["present", grillePresents],
            ["absent", grilleAbsents],
        ];

        for (const [nom, grille] of groupes) {
            const total = grille.querySelectorAll(".product-card").length;

            catalogue.querySelector(
                `[data-count="${nom}"]`
            ).textContent = String(total);

            catalogue.querySelector(
                `[data-empty="${nom}"]`
            ).hidden = total > 0;
        }
    }


    // Déplace une carte entre les deux sections quand elle passe par zéro.
    function replace(carte, quantite) {
        const boutonMoins = carte.querySelector(".step-down");

        carte.classList.toggle("is-empty", quantite === 0);
        boutonMoins.disabled = quantite === 0;

        const destination = quantite > 0 ? grillePresents : grilleAbsents;

        if (carte.parentElement !== destination) {
            insereTriee(destination, carte);
            rafraichitCompteurs();
        }
    }


    // Envoie au serveur le total du mouvement et recale la carte.
    async function enregistre(carte) {
        const attendue = quantiteAffichee(carte);
        const confirmee = quantiteConfirmee(carte);
        const mouvement = attendue - confirmee;

        if (mouvement === 0) {
            return;
        }

        const boutons = carte.querySelectorAll(".step");

        for (const bouton of boutons) {
            bouton.disabled = true;
        }

        try {
            const reponse = await fetch(URL_MOUVEMENT, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": JETON_CSRF,
                },
                body: JSON.stringify({
                    product_id: Number(carte.dataset.productId),
                    amount: mouvement,
                }),
            });

            const donnees = await reponse.json();

            // Le serveur fait foi, y compris quand il refuse.
            const quantite = typeof donnees.quantity === "number"
                ? donnees.quantity
                : confirmee;

            carte.dataset.confirmed = String(quantite);
            afficheQuantite(carte, quantite);
            replace(carte, quantite);

            if (!donnees.success) {
                signale(donnees.message || "Le mouvement a été refusé.");
            }

        } catch (panne) {
            // Réseau coupé ou réponse illisible : on revient au dernier
            // état connu du serveur plutôt que de mentir à l'utilisateur.
            afficheQuantite(carte, confirmee);
            replace(carte, confirmee);
            signale("Le serveur est injoignable. Le stock n'a pas changé.");

        } finally {
            for (const bouton of boutons) {
                bouton.disabled = false;
            }

            // Le bouton « moins » reste inactif à zéro.
            carte.querySelector(".step-down").disabled =
                quantiteAffichee(carte) === 0;
        }
    }


    // Applique un pas à l'écran, sans jamais descendre sous zéro.
    function avance() {
        const suivante = quantiteAffichee(appui.carte) + appui.sens;

        if (suivante < 0) {
            return false;
        }

        afficheQuantite(appui.carte, suivante);
        appui.pas += 1;

        return true;
    }


    // Programme le pas suivant, plus rapide au-delà d'un certain nombre.
    function programme() {
        const cadence = appui.pas >= PAS_AVANT_ACCELERATION
            ? CADENCE_RAPIDE
            : CADENCE_NORMALE;

        appui.minuteur = window.setTimeout(function () {
            if (!avance()) {
                return;
            }

            programme();
        }, cadence);
    }


    // Début d'appui : un pas immédiat, puis la répétition après un délai.
    function commence(carte, sens) {
        appui = { carte: carte, sens: sens, pas: 0, minuteur: null };

        if (!avance()) {
            appui = null;
            return;
        }

        pulse(carte, sens);

        appui.minuteur = window.setTimeout(
            programme,
            DELAI_AVANT_REPETITION
        );
    }


    // Fin d'appui : on arrête la répétition et on prévient le serveur.
    function termine() {
        if (appui === null) {
            return;
        }

        window.clearTimeout(appui.minuteur);

        const carte = appui.carte;
        appui = null;

        enregistre(carte);
    }


    catalogue.addEventListener("pointerdown", function (evenement) {
        const bouton = evenement.target.closest(".step");

        if (bouton === null || bouton.disabled) {
            return;
        }

        // Évite la sélection de texte pendant un appui maintenu.
        evenement.preventDefault();

        // Garde le pointeur lié au bouton même si le doigt glisse.
        bouton.setPointerCapture(evenement.pointerId);

        commence(
            bouton.closest(".product-card"),
            Number(bouton.dataset.step)
        );
    });

    for (const evenement of ["pointerup", "pointercancel"]) {
        catalogue.addEventListener(evenement, termine);
    }

    // Un appui maintenu ne doit pas ouvrir le menu contextuel du mobile.
    catalogue.addEventListener("contextmenu", function (evenement) {
        if (evenement.target.closest(".step") !== null) {
            evenement.preventDefault();
        }
    });
})();
