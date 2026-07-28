"use strict";

// Adresse publique du service IA vue depuis le navigateur.
// À adapter si le service IA est exposé sur une autre adresse.
const AI_QUERY_URL = "http://localhost:8001/api/query";
const AI_PRODUCTS_URL = "http://localhost:8001/api/products";
const CONVERSATION_STORAGE_KEY = "hbntory-conversation-id";

// Produits disposant de leur propre illustration, dans img/products/,
// nommée d'après l'identifiant du produit. Un produit absent de cette
// liste utilise l'image de sa catégorie.
const PRODUCTS_WITH_IMAGE = new Set([
    1, 2, 3, 4, 5, 6, 7, 8, 9, 10,
    11, 12, 13, 14, 15, 16, 17, 18, 19, 20,
    21, 22, 23, 24, 25, 26, 27, 28, 29, 30,
    31, 33, 34, 35, 36, 37, 38, 39, 40,
]);

const CATEGORY_IMAGES = {
    "Accessories": "img/categories/accessories.webp",
    "Audio": "img/categories/audio.webp",
    "Development Kits": "img/categories/development-kits.webp",
    "Displays": "img/categories/displays.webp",
    "Furniture": "img/categories/furniture.webp",
    "Laptops": "img/categories/laptops.webp",
    "Mobile Devices": "img/categories/mobile-devices.webp",
    "Networking": "img/categories/networking.webp",
    "Operations": "img/categories/operations.webp",
    "Power": "img/categories/power.webp",
    "Security": "img/categories/security.webp",
    "Storage": "img/categories/storage.webp",
    "Video": "img/categories/video.webp",
};

const DEFAULT_CATEGORY_IMAGE = "img/categories/default.webp";

// Récupère les éléments manipulés par le script.
const form = document.getElementById("question-form");
const input = document.getElementById("question");
const submitButton = document.getElementById("submit-button");
const loading = document.getElementById("loading");
const answer = document.getElementById("answer");
const error = document.getElementById("error");

// Éléments du catalogue affiché sous l'assistant.
const catalogStatus = document.getElementById("catalog-status");
const catalogGrid = document.getElementById("catalog-grid");
let conversationId = null;

try {
    conversationId = sessionStorage.getItem(
        CONVERSATION_STORAGE_KEY
    );
} catch (storageError) {
    // Une politique navigateur stricte ne doit pas bloquer l'assistant.
    conversationId = null;
}


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


// Affiche le texte naturel du service après l'avoir échappé.
// Le seul enrichissement HTML autorisé met un nom entre guillemets en gras.
function formatAnswerHtml(data) {
    const escaped = escapeHtml(data.answer);

    if (data.type === "product_details") {
        return escaped.replace(/«\s*([^»]+?)\s*»/, "<strong>$1</strong>");
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
    const payload = { question: question };

    if (conversationId) {
        payload.conversation_id = conversationId;
    }

    const response = await fetch(AI_QUERY_URL, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
    });
    const data = await response.json();

    // Le serveur peut renouveler un identifiant expiré. L'onglet utilise
    // toujours la dernière valeur opaque sans l'exposer dans l'URL.
    if (typeof data.conversation_id === "string") {
        conversationId = data.conversation_id;

        try {
            sessionStorage.setItem(
                CONVERSATION_STORAGE_KEY,
                conversationId
            );
        } catch (storageError) {
            // La conversation continue en mémoire pour l'onglet courant.
        }
    }

    // Conserve uniquement le message public structuré du service IA.
    if (!response.ok) {
        const publicError = new Error(
            data.answer
            || data.error?.message
            || "Une erreur est survenue."
        );
        publicError.isPublic = true;

        throw publicError;
    }

    return data;
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

    } catch (requestError) {
        // Ne montre jamais le détail technique d'une panne réseau ou JSON.
        const message = requestError.isPublic
            ? requestError.message
            : "Impossible de contacter le service. Réessayez plus tard.";

        showError(message);

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


// Met en forme un prix avec sa devise, ou un tiret si absent.
function formatPrice(product) {
    if (typeof product.unit_price !== "number") {
        return "—";
    }

    return product.unit_price.toFixed(2) + " " + (product.currency || "");
}


// Retourne l'illustration propre au produit, celle de sa catégorie,
// ou l'illustration de repli.
function productImage(product) {
    if (PRODUCTS_WITH_IMAGE.has(product.id)) {
        return "img/products/" + product.id + ".webp";
    }

    return CATEGORY_IMAGES[product.category] || DEFAULT_CATEGORY_IMAGE;
}


// Construit la zone image d'une carte.
function buildCardMedia(product) {
    const media = document.createElement("span");
    const image = document.createElement("img");

    media.className = "product-card-media";
    image.className = "product-card-image";
    image.src = productImage(product);
    image.loading = "lazy";
    image.alt = "";
    media.appendChild(image);

    return media;
}


// Construit le nom et le prix affichés sous l'image.
function buildCardBody(product) {
    const body = document.createElement("span");
    const name = document.createElement("span");
    const price = document.createElement("span");

    body.className = "product-card-body";
    name.className = "product-card-name";
    name.textContent = product.name || "—";
    price.className = "product-card-price";
    price.textContent = formatPrice(product);
    body.appendChild(name);
    body.appendChild(price);

    return body;
}


// Construit une carte produit : le clic prépare une question de stock
// dans l'assistant sans l'envoyer automatiquement.
function buildProductCard(product) {
    const item = document.createElement("li");
    const card = document.createElement("button");

    card.type = "button";
    card.className = "product-card";
    card.appendChild(buildCardMedia(product));
    card.appendChild(buildCardBody(product));
    card.addEventListener("click", function () {
        fillQuestion(
            "Où puis-je trouver le produit " + product.id + " ?"
        );
    });
    item.appendChild(card);

    return item;
}


// Charge le catalogue technique sans consommer de génération IA.
async function loadCatalog() {
    try {
        const response = await fetch(
            AI_PRODUCTS_URL + "?limit=100&offset=0"
        );
        const data = await response.json();

        if (!response.ok || !data.success) {
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
            catalogGrid.appendChild(buildProductCard(product));
        }

        // Remplace le message de chargement par la grille remplie.
        catalogStatus.hidden = true;
        catalogGrid.hidden = false;

    } catch (networkError) {
        catalogStatus.textContent =
            "Impossible de charger le catalogue. Réessayez plus tard.";
    }
}


form.addEventListener("submit", handleSubmit);
loadCatalog();
