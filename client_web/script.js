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


// Affiche la réponse renvoyée par le service IA.
function showAnswer(message) {
    answer.textContent = message;
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


// Gère l'envoi du formulaire.
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
            showAnswer(data.answer);
        } else {
            showError(data.error || "Une erreur est survenue.");
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


form.addEventListener("submit", handleSubmit);
