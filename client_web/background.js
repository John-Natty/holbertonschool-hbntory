"use strict";

// Pluie numérique façon Matrix, aux couleurs cyan et jaune.
(function () {
    const canvas = document.getElementById("matrix");

    if (!canvas) {
        return;
    }

    const ctx = canvas.getContext("2d");

    // Caractères qui défilent : katakana, chiffres et symboles.
    const GLYPHS = (
        "アカサタナハマヤラワ0123456789ABCDEF<>/\\[]{}#$*+="
    ).split("");

    const FONT_SIZE = 16;
    const CYAN = "#10c6e6";
    const YELLOW = "#f4ec00";

    // Nombre de traînées par colonne : monte = pluie plus dense.
    const DENSITE = 1.8;

    // Proportion de traînées jaunes : monte = plus de jaune.
    const PART_JAUNE = 0.55;

    let columns = 0;
    let streams = [];

    // Crée une nouvelle traînée à une colonne et une hauteur aléatoires.
    function newStream() {
        return {
            x: Math.floor(Math.random() * columns) * FONT_SIZE,
            y: Math.floor(Math.random() * -60),
            color: Math.random() < PART_JAUNE ? YELLOW : CYAN,
        };
    }

    // Recalcule le nombre de colonnes et de traînées selon la fenêtre.
    function resize() {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
        columns = Math.floor(canvas.width / FONT_SIZE);

        const count = Math.floor(columns * DENSITE);
        streams = [];

        for (let i = 0; i < count; i++) {
            streams.push(newStream());
        }
    }

    // Dessine une image de la pluie.
    function draw() {
        // Voile sombre semi-transparent : efface peu à peu la traînée.
        ctx.fillStyle = "rgba(5, 6, 10, 0.08)";
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        ctx.font = FONT_SIZE + "px monospace";

        for (const stream of streams) {
            const glyph = GLYPHS[Math.floor(Math.random() * GLYPHS.length)];

            ctx.fillStyle = stream.color;
            ctx.fillText(glyph, stream.x, stream.y * FONT_SIZE);

            // Relance la traînée en haut, à une nouvelle colonne au hasard.
            if (
                stream.y * FONT_SIZE > canvas.height
                && Math.random() > 0.975
            ) {
                stream.y = 0;
                stream.x = Math.floor(Math.random() * columns) * FONT_SIZE;
                stream.color = Math.random() < PART_JAUNE ? YELLOW : CYAN;
            }

            stream.y++;
        }
    }

    resize();
    window.addEventListener("resize", resize);

    // Respecte le réglage système « animations réduites ».
    const reduced = window.matchMedia(
        "(prefers-reduced-motion: reduce)"
    ).matches;

    if (reduced) {
        // Fond sombre fixe, sans animation.
        ctx.fillStyle = "#05060a";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        return;
    }

    // Cadence de l'animation : monte = plus lent, baisse = plus rapide.
    setInterval(draw, 90);
})();
