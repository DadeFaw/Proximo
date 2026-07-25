# Proximo — jeu de devinette par proximité sémantique

Application web **multijoueur** (2 joueurs et plus) où l'on devine un **mot cible** :
à chaque proposition, le système renvoie un **pourcentage de proximité sémantique**
(rang percentile) avec la cible. Manches **simultanées en aveugle**, salons par code
+ QR, moteur sémantique **français** opérationnel. Implémentation complète du
[brief](brief-jeu-semantique.md).

> État : **fonctionnel et testé de bout en bout** (moteur sémantique, boucle de
> manches, scoring/égalités, WebSocket, reconnexion, client PWA installable).

---

## 1. Démarrage rapide

### Option A — Windows (Python seul, tel que développé)

Prérequis : **Python 3.12+**. (Node et Redis **ne sont pas nécessaires**.)

```powershell
.\setup.ps1     # une fois : venv + dépendances + modèle spaCy + cache lexique
.\run.ps1       # lance semantic-api (8100) puis game-api (8000)
```

Puis ouvrir **http://127.0.0.1:8000**. Pour jouer à plusieurs sur le même PC,
ouvrez plusieurs onglets **en navigation privée séparée** (le `localStorage` est
partagé entre onglets normaux — en usage réel chaque joueur est sur son appareil).

### Option B — Docker (déploiement complet, avec Redis)

Prérequis : Docker + Docker Compose.

```bash
docker compose up --build
# puis http://localhost:8000
```

Le `compose` construit les deux services, précharge le modèle français et le cache,
et branche Redis comme store d'état (TTL 24 h).

### Option C — Linux/macOS sans Docker

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r semantic-api/requirements.txt -r game-api/requirements.txt
python -m spacy download fr_core_news_md
./run.sh
```

---

## 2. Comment jouer

1. **Créer une partie** : choisir le mode (`Le système` tire le mot / `Un joueur`
   le saisit), le **thème** du mot cible (Animaux, Nourriture, Nature… ou Aléatoire)
   et le niveau (`Facile` 10 manches / `Normal` 6 / `Difficile` 3).
2. **Partager** le code à 6 caractères ou faire **scanner le QR**. Chaque joueur
   rejoint depuis son appareil.
3. En mode `Un joueur`, l'hôte **saisit et valide** le mot cible (nom commun, connu
   du dictionnaire) — il ne devine pas cette partie.
4. L'hôte **lance**. À chaque manche : **25 s**, une seule proposition par joueur.
   À l'expiration (ou dès que tout le monde a proposé), **toutes les propositions et
   leur pourcentage de proximité sémantique** sont révélés simultanément.
5. Entre les manches, c'est **l'hôte qui lance la manche suivante** (bouton
   « Manche suivante → »). Les **points/classement restent cachés** pendant la partie.
6. La partie s'arrête quand quelqu'un trouve la cible, ou au bout des N manches.
   Alors seulement le **classement au cumul** (« 🏆 Voir les résultats ») et le mot
   cible sont dévoilés. Deux vues finales : **Classement** et **Chronologique**.

---

## 3. Architecture

| Service | Rôle | Techno | Port |
|---|---|---|---|
| `semantic-api` | Vecteurs en RAM, percentiles, validation lexicale, tirage | Python / FastAPI + spaCy + numpy | 8100 |
| `game-api` | Salons, manches, timer, scoring, WebSocket, QR, sert la PWA | Python / FastAPI | 8000 |
| `store` | État de partie éphémère | **mémoire** (défaut) ou **Redis** (TTL 24 h) | — |
| `client` | Interface joueur, PWA installable | Preact + htm (sans build) | servi par 8000 |

```
Navigateur (PWA)  ⇄  game-api  ⇄  semantic-api
   WebSocket /ws      REST /api      /normalize /percentiles /random-word
                       + store          (lexique 300d en RAM)
                    (mémoire/Redis)
```

**Autorité serveur** (brief §4.2) : le serveur est seul détenteur du mot cible, du
compteur de manches et du **buffer de propositions** de la manche en cours. Le
client ne reçoit que des scores et l'historique **déjà révélé**. Le mot cible n'est
transmis qu'à l'événement `gameFinished`.

### Écarts assumés vis-à-vis du brief (et pourquoi)

Le brief propose une architecture indicative ; les critères d'acceptation portent
sur le **comportement**, tous satisfaits. Les choix ci-dessous rendent le livrable
immédiatement exécutable sur la machine cible (Windows, sans Node/Redis/Docker) :

| Brief | Ici | Raison |
|---|---|---|
| `game-api` en Node/Fastify **ou** FastAPI | **FastAPI** | Le brief l'autorise ; une seule stack (Python), zéro Node à installer. |
| Client **React + Vite** | **Preact + htm** vendorisé, **sans build** | API quasi identique à React (hooks/JSX). Tourne sans Node ni bundler ; reste une PWA installable. Portage vers Vite trivial. |
| Store **Redis** | **Mémoire** par défaut, **Redis** si `REDIS_URL` | Jouable sans dépendance ; Redis activé en un env var (et par défaut dans Docker). |
| Modèle **frWac / cc.fr.300**, ~80 000 lemmes | **spaCy `fr_core_news_md`** (17 k vrais vecteurs 300d) par défaut, **+ script d'élagage** pour la voie 80 k | Un seul téléchargement (~43 Mo) fournissant vecteurs + lemmatisation + noms propres. Voir §4. |

---

## 4. Moteur sémantique (le composant critique)

### Ce qui est en place

- **Vecteurs statiques français 300d** chargés en RAM (pas de sentence-transformer).
- **Pourcentage = rang percentile** (brief §3.2) : au lancement, une seule passe
  `numpy.dot` de la cible contre tout le lexique, tri, dictionnaire `{mot: percentile}`
  en mémoire de partie ; chaque proposition est ensuite un **lookup O(1)**.
  Similarité normalisée sur `[0, 1]`, distribution **étalée** (ex. face à *chat* :
  `chien` 99.99, `animal` 99.9, `table` 93, `avion` 76, `démocratie` 12).
- **Normalisation des entrées** (brief §3.3) : minuscules/trim → **lemmatisation
  spaCy** → recherche vocabulaire → **seconde tentative désaccentuée** → sinon
  **rejet explicite** (« mot inconnu du dictionnaire »), **sans consommer** la
  proposition. Les **noms propres** sont refusés. Jamais de score 0 pour un
  hors-vocabulaire.
- Le lexique sert simultanément de vocabulaire de percentiles, référentiel de
  validation, et vivier de tirage par niveau (noms communs, en forme canonique).
- **Cache disque** du lexique (matrice + POS + lemmes) : le filtrage n'est fait
  **qu'une fois**, pas à chaque démarrage (brief §3.1).

### Qualité et limites du modèle par défaut

`fr_core_news_md` élague ses vecteurs (~500 k clés remappées sur 20 000 lignes) : on
ne conserve donc qu'**un mot par vecteur réel unique** (~17 k lemmes), ce qui donne
des voisinages **réellement sémantiques**. Limites assumées en V1 :

- Vocabulaire de ~17 k mots : certaines propositions valides mais rares sont
  refusées. La **concrétude** des niveaux est approximée par la **fréquence**.
- Léger bruit de corpus résiduel sur quelques tokens.

### Passage à l'échelle (voie « brief » 80 000 lemmes)

Deux options, sans changer le code du jeu :

1. **Modèle spaCy plus riche** — `fr_core_news_lg` (500 k vecteurs réels) :
   ```powershell
   .\.venv\Scripts\python.exe -m spacy download fr_core_news_lg
   $env:SPACY_MODEL = "fr_core_news_lg"   # puis relancer
   ```
   Le lexique est automatiquement borné aux `MAX_LEXICON` (80 000) lemmes les plus
   fréquents.

2. **Artefact élagué frWac / cc.fr.300** (brief §3.1, §9.1) via le script fourni :
   ```bash
   python semantic-api/prune_model.py --model cc.fr.300.bin --format fasttext \
          --out semantic-api/artifact --limit 80000
   # puis démarrer le service : ARTIFACT_DIR=semantic-api/artifact
   ```
   Produit `vectors.npy` + `words.json` (+ `ranks.npy`), ~100 Mo, chargé directement
   au boot. S'il est présent, il **prime** sur le modèle spaCy.

---

## 5. Protocole WebSocket (brief §6)

**Client → serveur :** `join`, `leave`, `setTargetWord`, `startGame`, `submitGuess`
**Serveur → clients :** `joined`, `state`, `lobbyUpdate`, `gameStarted`,
`roundStarted` (avec `deadline`), `roundRevealed` (propositions + scores de tous),
`gameFinished` (mot cible + classement), `guessAccepted`, `targetSet`, `error`.

Reconnexion : le client mémorise `{code, playerId}` et se reconnecte
automatiquement ; le serveur restaure l'état et l'historique déjà révélé.

### État de partie (store, brief §5)

`game:{code}` = `{ code, mode, level, totalRounds, currentRound, status, targetWord
(jamais avant FINISHED), wordSetterId, hostId, players[], roundBuffer (vidé à chaque
révélation), history[], roundDeadline }`.

---

## 6. Tests

```powershell
# Ressenti sémantique (voisinages, distribution, normalisation, tirage)
.\.venv\Scripts\python.exe semantic-api\tests\smoke_engine.py

# Scoring et règles d'égalité (unitaires, sans serveur)
.\.venv\Scripts\python.exe game-api\tests\test_scoring.py

# Intégration bout-en-bout (serveurs 8100 + 8000 démarrés) :
#  - aucune fuite du mot cible avant la fin
#  - aveugle (aucune proposition adverse avant révélation)
#  - mot invalide rejeté sans consommer le tour
#  - N manches, scoring, mode PLAYER
.\.venv\Scripts\python.exe game-api\tests\integration_game.py
```

---

## 7. Critères d'acceptation (brief §7)

| Critère | Statut |
|---|---|
| Partie à 2 joueurs distants, intégrale, sans intervention | ✅ |
| Partie à 4 joueurs sur 4 appareils, rejoints par QR | ✅ (jusqu'à 12 joueurs) |
| Modes `SYSTEM` et `PLAYER` fonctionnels | ✅ |
| Niveaux appliquant 10 / 6 / 3 manches | ✅ |
| Aucune proposition visible avant l'expiration du timer | ✅ (buffer serveur, vérifié) |
| Mot cible absent du trafic client avant `gameFinished` | ✅ (vérifié en test) |
| Mot hors-vocabulaire rejeté sans consommer la proposition | ✅ |
| Deux joueurs, même mot → tous deux marquent | ✅ |
| Deux joueurs à égalité au meilleur % → 50 % chacun | ✅ |
| Déconnexion sans interruption + reconnexion + historique | ✅ |
| Scores = percentiles à distribution étalée | ✅ |

---

## 8. Configuration (variables d'environnement)

**semantic-api** : `SPACY_MODEL` (défaut `fr_core_news_md`), `ARTIFACT_DIR`,
`MAX_LEXICON` (80000), `MIN_WORD_LEN` (3), `SEMANTIC_PORT` (8100).

**game-api** : `SEMANTIC_API_URL`, `REDIS_URL` (sinon mémoire), `STATE_TTL` (86400),
`ROUND_SECONDS` (25), `REVEAL_PAUSE_SECONDS` (4), `PUBLIC_BASE_URL` (pour les QR),
`CLIENT_DIR`, `GAME_PORT` (8000).

---

## 9. Hors périmètre V1 (brief §8)

Comptes/auth, classements inter-parties, chat, modes additionnels, i18n.
**Français uniquement.**

## 10. Structure du projet

```
semantic-api/   moteur sémantique (engine.py), API, prune_model.py, tests
game-api/       runtime.py (manches/timer), scoring.py, store.py, main.py, tests
client/         PWA sans build : index.html, app.js, styles.css, sw.js, vendor/, icons/
docker-compose.yml · setup.ps1 · run.ps1 · run.sh
```
