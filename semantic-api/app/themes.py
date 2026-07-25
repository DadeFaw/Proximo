"""Thèmes de jeu : listes de mots cibles candidats par catégorie (mode SYSTEM).

Le mot cible est tiré dans le thème choisi par l'hôte. À l'initialisation du
moteur, chaque liste est filtrée pour ne conserver que les mots réellement
présents dans le vocabulaire (voir engine.build_theme_pools)."""
from __future__ import annotations

THEMES: dict[str, dict] = {
    "ALEATOIRE": {"label": "Aléatoire", "emoji": "🎲", "words": []},  # tirage par niveau
    "ANIMAUX": {"label": "Animaux", "emoji": "🐾", "words": [
        "chat", "chien", "lion", "tigre", "cheval", "vache", "mouton", "poule",
        "canard", "souris", "éléphant", "girafe", "singe", "ours", "loup", "renard",
        "lapin", "oiseau", "poisson", "requin", "dauphin", "serpent", "araignée",
        "abeille", "papillon", "grenouille", "tortue", "aigle", "hibou", "cochon",
        "âne", "chèvre", "poulet", "baleine", "crocodile", "kangourou", "écureuil"]},
    "NOURRITURE": {"label": "Nourriture", "emoji": "🍎", "words": [
        "pain", "fromage", "pomme", "banane", "tomate", "carotte", "poulet", "riz",
        "gâteau", "chocolat", "café", "thé", "lait", "œuf", "sucre", "sel", "soupe",
        "salade", "viande", "jambon", "beurre", "miel", "orange", "fraise", "citron",
        "poire", "pâtes", "pizza", "sandwich", "yaourt", "confiture", "farine",
        "baguette", "légume", "fruit", "dessert", "sauce", "huile", "vin"]},
    "NATURE": {"label": "Nature", "emoji": "🌳", "words": [
        "montagne", "rivière", "forêt", "arbre", "fleur", "mer", "océan", "plage",
        "désert", "volcan", "nuage", "pluie", "neige", "soleil", "lune", "étoile",
        "vent", "orage", "lac", "colline", "vallée", "herbe", "feuille", "racine",
        "rocher", "sable", "vague", "ciel", "terre", "prairie", "cascade", "glace"]},
    "SPORT": {"label": "Sport", "emoji": "⚽", "words": [
        "football", "tennis", "natation", "course", "vélo", "boxe", "ski", "danse",
        "basket", "rugby", "golf", "judo", "cyclisme", "marathon", "gymnastique",
        "escalade", "plongée", "voile", "équitation", "athlétisme", "handball",
        "ballon", "match", "équipe", "victoire", "champion", "stade", "arbitre"]},
    "MUSIQUE": {"label": "Musique", "emoji": "🎵", "words": [
        "guitare", "piano", "violon", "batterie", "flûte", "trompette", "chanson",
        "concert", "orchestre", "mélodie", "rythme", "note", "chœur", "opéra",
        "jazz", "rock", "musique", "danse", "voix", "harmonie", "accord", "disque"]},
    "MAISON": {"label": "Maison", "emoji": "🏠", "words": [
        "table", "chaise", "lit", "canapé", "fenêtre", "porte", "cuisine", "chambre",
        "salon", "jardin", "toit", "mur", "escalier", "lampe", "miroir", "armoire",
        "four", "évier", "tapis", "rideau", "coussin", "étagère", "bureau", "clé",
        "horloge", "vase", "couverture", "oreiller", "balcon", "garage", "cave"]},
    "CORPS": {"label": "Corps humain", "emoji": "🖐️", "words": [
        "tête", "main", "pied", "bras", "jambe", "œil", "oreille", "nez", "bouche",
        "dent", "cheveu", "cœur", "cerveau", "doigt", "épaule", "genou", "dos",
        "ventre", "cou", "langue", "peau", "os", "muscle", "sang", "poumon", "front"]},
    "TRANSPORT": {"label": "Transports", "emoji": "🚗", "words": [
        "voiture", "train", "avion", "bateau", "vélo", "moto", "bus", "camion",
        "métro", "tramway", "hélicoptère", "fusée", "scooter", "taxi", "voilier",
        "wagon", "route", "autoroute", "gare", "aéroport", "port", "carburant"]},
    "METIERS": {"label": "Métiers", "emoji": "💼", "words": [
        "médecin", "professeur", "boulanger", "pompier", "policier", "avocat",
        "ingénieur", "cuisinier", "agriculteur", "artiste", "musicien", "plombier",
        "électricien", "journaliste", "infirmier", "pilote", "facteur", "coiffeur",
        "peintre", "architecte", "vétérinaire", "jardinier", "serveur", "pêcheur"]},
    "EMOTIONS": {"label": "Émotions", "emoji": "😊", "words": [
        "joie", "tristesse", "colère", "peur", "amour", "haine", "surprise",
        "bonheur", "angoisse", "jalousie", "fierté", "honte", "espoir", "ennui",
        "plaisir", "douleur", "courage", "passion", "tendresse", "nostalgie",
        "envie", "gratitude", "sérénité", "excitation", "déception", "confiance"]},
    "COULEURS": {"label": "Couleurs", "emoji": "🎨", "words": [
        "rouge", "bleu", "vert", "jaune", "orange", "violet", "rose", "noir",
        "blanc", "gris", "marron", "beige", "turquoise", "pourpre", "doré",
        "argenté", "bordeaux", "indigo", "corail", "émeraude"]},
}
