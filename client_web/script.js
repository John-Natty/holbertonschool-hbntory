"use strict";

// Adresse publique du service IA vue depuis le navigateur.
// À adapter si le service IA est exposé sur une autre adresse.
const AI_QUERY_URL = "http://localhost:8001/api/query";

// Récupère les éléments manipulés par le script.
const form = document.getElementById("question-form");
const input = document.getElementById("question");
const submitButton = document.getElementById("submit-button");
const loading = document.getElementById("loading");
const answer = document.getElementById("answer");
const error = document.getElementById("error");

// Éléments du panneau catalogue (colonne de droite).
const catalogStatus = document.getElementById("catalog-status");
const catalogList = document.getElementById("catalog-list");


// Masque la réponse et l'erreur avant chaque nouvelle recherche.
function resetOutput() {
    answer.hidden = true;
    answer.textContent = "";
    error.hidden = true;
    error.textContent = "";
}


// Affiche un message d'erreur lisible pour l'utilisateur.
function showError(message) {
    error.textContent = message;
    error.hidden = false;
}


// Échappe un texte pour une insertion HTML sûre.
function escapeHtml(text) {
    const container = document.createElement("div");
    container.textContent = text;
    return container.innerHTML;
}


// Décrit une branche par son nom (« la branche de Toulouse »), avec
// l'élision « d' » devant une voyelle (« la branche d'Albi »).
// Fonctionne pour n'importe quelle branche, y compris une future.
function describeBranch(branchName) {
    const startsWithVowel = /^[aeiouyàâäéèêëîïôöùûü]/i.test(branchName);
    const preposition = startsWithVowel ? "d’" : "de ";

    return "la branche " + preposition + escapeHtml(branchName);
}


// Met en majuscule la première lettre d'une phrase.
function capitalize(text) {
    return text.charAt(0).toUpperCase() + text.slice(1);
}


// Met en forme la réponse :
// - détail d'un produit : retire les guillemets françaises autour du
//   nom et le met en gras ;
// - stock disponible dans une seule branche : nomme cette branche au
//   lieu de se contenter de « 1 branche » ;
// - liste d'achats satisfaite par une seule branche : idem.
function formatAnswerHtml(data) {
    const escaped = escapeHtml(data.answer);

    if (data.type === "product_details") {
        return escaped.replace(/«\s*([^»]+?)\s*»/, "<strong>$1</strong>");
    }

    if (data.type === "stock_by_product" && data.data.branches.length === 1) {
        const branchName = data.data.branches[0].branch_name;

        return (
            "Le produit " + data.data.product_id + " est disponible dans "
            + describeBranch(branchName) + "."
        );
    }

    if (
        data.type === "shopping_list"
        && data.data.matching_branches.length === 1
    ) {
        const branchName = data.data.matching_branches[0].branch_name;

        return (
            capitalize(describeBranch(branchName))
            + " peut satisfaire entièrement cette liste d’achats."
        );
    }

    return escaped;
}


// Affiche la réponse renvoyée par le service IA.
function showAnswer(data) {
    answer.innerHTML = formatAnswerHtml(data);
    answer.hidden = false;
}


// Active ou désactive le formulaire pendant une recherche.
function setBusy(isBusy) {
    submitButton.disabled = isBusy;
    input.disabled = isBusy;
    loading.hidden = !isBusy;
}


// Interroge le service IA et retourne sa réponse JSON.
async function askQuestion(question) {
    const response = await fetch(AI_QUERY_URL, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({ question: question }),
    });

    // Une réponse HTTP en erreur est signalée clairement.
    if (!response.ok) {
        throw new Error(
            "Le service a répondu avec le code " + response.status + "."
        );
    }

    return response.json();
}


// Gère l'envoi du formulaire. Seul ce chemin interroge le service IA.
async function handleSubmit(event) {
    // Empêche le rechargement de la page par le navigateur.
    event.preventDefault();

    const question = input.value.trim();

    // Ignore une question vide.
    if (!question) {
        return;
    }

    resetOutput();
    setBusy(true);

    try {
        const data = await askQuestion(question);

        // Le service indique lui-même si la requête a réussi.
        if (data.success) {
            showAnswer(data);
        } else {
            // Le service fournit un message lisible dans « answer »,
            // même lorsque la requête échoue.
            showError(data.answer || "Une erreur est survenue.");
        }

    } catch (networkError) {
        // Couvre les pannes réseau et les réponses illisibles.
        showError(
            "Impossible de contacter le service. Réessayez plus tard."
        );

    } finally {
        // Réactive toujours le formulaire, même en cas d'erreur.
        setBusy(false);
    }
}


// Place une phrase dans le champ de l'assistant, sans jamais l'envoyer.
// L'utilisateur reste seul décisionnaire de l'envoi.
function fillQuestion(question) {
    input.value = question;
    input.focus();
}


// Relie chaque commande du panneau gauche au champ de l'assistant.
function bindCommandButtons() {
    const buttons = document.querySelectorAll(".cmd-item");

    for (const button of buttons) {
        button.addEventListener("click", function () {
            fillQuestion(button.textContent.trim());
        });
    }
}


// Met en forme un prix avec sa devise, ou un tiret si absent.
function formatPrice(product) {
    if (typeof product.unit_price !== "number") {
        return "—";
    }

    return product.unit_price.toFixed(2) + " " + (product.currency || "");
}


// Construit une entrée du catalogue : le clic compose la question
// de stock correspondante dans l'assistant, sans l'envoyer.
function buildCatalogItem(product) {
    const item = document.createElement("li");
    const button = document.createElement("button");

    button.type = "button";
    button.className = "catalog-item";

    const idSpan = document.createElement("span");
    idSpan.className = "catalog-item-id";
    idSpan.textContent = "#" + product.id;

    const nameSpan = document.createElement("span");
    nameSpan.className = "catalog-item-name";
    nameSpan.textContent = product.name || "—";

    const priceSpan = document.createElement("span");
    priceSpan.className = "catalog-item-price";
    priceSpan.textContent = formatPrice(product);

    button.appendChild(idSpan);
    button.appendChild(nameSpan);
    button.appendChild(priceSpan);

    button.addEventListener("click", function () {
        fillQuestion("stock du produit " + product.id);
    });

    item.appendChild(button);

    return item;
}


// Charge le catalogue au démarrage, via l'assistant IA lui-même,
// et l'affiche dans le panneau de droite.
async function loadCatalog() {
    try {
        // Une seule requête suffit : la limite maximale du service est 100.
        const data = await askQuestion("liste les 100 premiers produits");

        if (!data.success || data.type !== "product_list") {
            catalogStatus.textContent =
                "Catalogue indisponible pour le moment.";
            return;
        }

        const products = data.data.products || [];

        if (products.length === 0) {
            catalogStatus.textContent =
                "Aucun produit dans le catalogue.";
            return;
        }

        for (const product of products) {
            catalogList.appendChild(buildCatalogItem(product));
        }

        // Remplace le message de chargement par la liste remplie.
        catalogStatus.hidden = true;
        catalogList.hidden = false;

    } catch (networkError) {
        catalogStatus.textContent =
            "Impossible de charger le catalogue. Réessayez plus tard.";
    }
}


form.addEventListener("submit", handleSubmit);
bindCommandButtons();
loadCatalog();
