# Brief de développement — Jeu de devinette par proximité sémantique

## 1. Objectif

Développer une application web multijoueur (2 joueurs minimum) dans laquelle les
joueurs tentent de deviner un mot cible. À chaque proposition, le système renvoie
un pourcentage de proximité sémantique avec le mot cible. Les joueurs peuvent être
au même endroit physique ou à distance : un seul mécanisme de salon couvre les deux
cas.

Livrable attendu : application fonctionnelle, déployable, avec moteur sémantique
français opérationnel.

---

## 2. Règles du jeu

### 2.1 Choix du mot cible — deux modes

| Mode | Description |
|---|---|
| `SYSTEM` | Le système tire le mot cible au hasard dans un lexique filtré par niveau. Tous les joueurs devinent. |
| `PLAYER` | Un joueur saisit le mot cible. Il ne participe pas aux propositions de la manche. |

En mode `PLAYER`, le mot saisi **doit être validé avant le lancement de la partie**
(présent dans le vocabulaire d'embeddings, nom commun, non nom propre). Un mot
invalide est refusé avec un message explicite, la partie n'est pas lancée.

### 2.2 Déroulement — manches simultanées en aveugle

Le déroulement est **simultané et non séquentiel**. Ce choix est validé et ferme :
il neutralise l'avantage d'information du dernier joueur, avantage qui est
structurel dès lors que tous les scores sont publics.

1. Une manche s'ouvre, un timer de 25 secondes démarre.
2. Chaque joueur actif saisit une proposition (une seule) pendant la fenêtre.
3. À l'expiration du timer, **toutes** les propositions et **tous** les scores sont
   révélés simultanément à l'ensemble des joueurs.
4. Manche suivante.

**Contrainte serveur impérative :** les propositions d'une manche sont bufferisées
côté serveur et ne sont diffusées qu'à l'expiration du timer. Aucune fuite avant
révélation, sinon l'aveugle ne tient pas.

Un joueur qui ne propose rien dans la fenêtre est simplement absent de la manche,
sans pénalité.

### 2.3 Niveaux et durée de partie

Une partie comporte N manches, N dépendant du niveau :

| Niveau | N (manches) | Mot cible |
|---|---|---|
| Facile | 10 | concret, très courant |
| Normal | 6 | courant, semi-abstrait |
| Difficile | 3 | abstrait, rare ou polysémique |

Le nombre de manches est indépendant du nombre de joueurs : chaque joueur dispose
donc exactement de N propositions, quelle que soit la taille du groupe.

### 2.4 Fin de partie

La partie s'arrête dès que l'une des conditions est remplie :

- un joueur au moins a trouvé le mot cible (fin immédiate à la révélation de la manche) ;
- les N manches ont été jouées.

### 2.5 Scoring

| Situation | Attribution |
|---|---|
| Le joueur trouve le mot cible | **1 point** |
| Personne ne trouve | Le joueur au meilleur pourcentage reçoit **50 % de ce pourcentage** en points (ex. 62 % → 0,31 point) |

**Règle générale des égalités : une égalité n'est jamais départagée, elle est
dupliquée.**

- Plusieurs joueurs trouvent le mot dans la même manche → 1 point chacun.
- Plusieurs joueurs proposent le même mot dans la même manche → les deux marquent
  normalement, aucune priorité au premier arrivé.
- Plusieurs joueurs à égalité au meilleur pourcentage → chacun reçoit 50 % de ce
  pourcentage.

Conséquence assumée : le total de points distribués par partie n'est pas constant.
Le classement se fait au cumul.

### 2.6 Visibilité

**Toutes les propositions et tous les scores de tous les joueurs sont visibles par
tout le monde**, dès la révélation de chaque manche. Deux vues doivent être
disponibles :

- **Chronologique** : le déroulé manche par manche, toutes propositions confondues.
- **Classement** : meilleur score atteint par joueur, tri décroissant. C'est la vue
  qui porte la tension du jeu, la soigner particulièrement.

Le mot cible n'est jamais transmis au client avant la fin de la partie.

---

## 3. Moteur sémantique

C'est le composant critique du projet. Une implémentation naïve rend le jeu
injouable.

### 3.1 Modèle

Utiliser des **embeddings statiques français** (word2vec ou FastText entraînés sur
corpus français, type frWac), dimension 300.

**Ne pas utiliser de sentence-transformer.** Les modèles de phrases lissent les
relations mot-à-mot et produisent des voisinages nettement moins intuitifs pour ce
cas d'usage.

**Le modèle doit être élagué au chargement**, et non embarqué intégralement :
conserver uniquement les ~80 000 lemmes les plus fréquents, filtrés sur les noms
communs, verbes, adjectifs et adverbes. On passe ainsi de plusieurs gigaoctets à
environ 100 Mo, ce qui allège radicalement le déploiement et l'empreinte mémoire.

Cet élagage est à faire **une fois, hors ligne**, dans un script dédié qui produit
un artefact binaire (matrice `numpy` + index des mots) chargé directement au
démarrage du service. Ne pas refaire le filtrage à chaque boot.

Le lexique élagué sert simultanément de : vocabulaire de calcul des percentiles,
référentiel de validation des propositions, et vivier de tirage du mot cible en
mode `SYSTEM`.

### 3.2 Calcul du pourcentage — rang percentile, pas cosinus brut

La similarité cosinus brute a une distribution écrasée : la grande majorité des
mots du lexique tombe entre 0,05 et 0,25 face à une cible donnée. Affichée telle
quelle, l'aiguille ne bouge quasiment jamais et le jeu est frustrant.

Le pourcentage affiché doit donc être un **rang percentile** :

1. Au lancement de la partie, calculer **une seule fois** la similarité cosinus du
   mot cible contre l'intégralité du lexique (~80 000 lemmes). Un `numpy.dot` sur
   une matrice 80k × 300 s'exécute en une dizaine de millisecondes.
2. Trier, et stocker en mémoire de partie un dictionnaire `{mot: percentile}`.
3. Chaque proposition devient un lookup O(1).

Aucun index de recherche approchée (ANN) n'est nécessaire.

Normaliser la similarité sur l'intervalle `[0, 1]` et non `[-1, 1]` : à défaut, des
pourcentages négatifs peuvent apparaître à l'affichage.

### 3.3 Normalisation des entrées

Pipeline appliqué à chaque proposition, dans cet ordre :

1. Passage en minuscules, trim.
2. Lemmatisation (spaCy `fr_core_news_sm`).
3. Recherche dans le vocabulaire ; en cas d'échec, seconde tentative sur une clé
   désaccentuée.
4. Si le mot reste introuvable, ou s'il s'agit d'un nom propre : **rejet explicite**
   avec message clair (« mot inconnu du dictionnaire »), et **la proposition n'est
   pas consommée** — le joueur peut ressaisir dans la fenêtre de temps restante.

Ne jamais renvoyer un score de 0 pour un mot hors vocabulaire : c'est la principale
source de frustration sur ce type de jeu.

---

## 4. Architecture

| Service | Rôle | Techno |
|---|---|---|
| `semantic-api` | Chargement des vecteurs, calcul des percentiles, validation lexicale | Python / FastAPI + gensim + spaCy |
| `game-api` | Salons, manches, timer, scoring, WebSocket | FastAPI ou Node/Fastify |
| `store` | État de partie éphémère | Redis, TTL 24 h |
| `client` | Interface joueur | PWA installable — React + Vite |

Points structurants :

- `semantic-api` porte le lexique élagué en RAM, soit environ 100 Mo une fois le
  modèle réduit aux 80 000 lemmes retenus (cf. § 3.1). Le maintenir isolé et
  scalable indépendamment du reste.
- L'état de partie va en **Redis, pas en base relationnelle**. Il est éphémère par
  nature.
- Le client est une **PWA installable**, pas d'application native ni de passage par
  les stores.

### 4.1 Salons

Un seul mécanisme couvre présentiel et distance : **code de salon à 6 caractères
alphanumériques + QR code**. Chaque joueur est sur son propre appareil, y compris
autour de la même table. Ne pas développer de mode « passe-plat » sur un appareil
unique.

### 4.2 Autorité serveur

Le serveur est seul détenteur du mot cible, du compteur de manches et du buffer de
propositions de la manche en cours. Le client ne reçoit que des scores et
l'historique déjà révélé. Aucune information exploitable ne doit transiter avant
révélation.

---

## 5. Modèle de données (état de partie, Redis)

```
game:{code} = {
  code:            string(6),
  mode:            "SYSTEM" | "PLAYER",
  level:           "FACILE" | "NORMAL" | "DIFFICILE",
  totalRounds:     int,
  currentRound:    int,
  status:          "LOBBY" | "RUNNING" | "REVEALING" | "FINISHED",
  targetWord:      string,          // jamais diffusé avant FINISHED
  wordSetterId:    string | null,   // mode PLAYER uniquement
  players:         [{ id, pseudo, score, connected }],
  roundBuffer:     [{ playerId, word }],          // vidé à chaque révélation
  history:         [{ round, playerId, word, percentile, isTarget }],
  roundDeadline:   timestamp
}
```

---

## 6. Événements WebSocket

**Client → serveur :** `join`, `leave`, `setTargetWord`, `startGame`, `submitGuess`

**Serveur → clients :** `lobbyUpdate`, `gameStarted`, `roundStarted` (avec deadline),
`roundRevealed` (propositions + scores de tous les joueurs), `gameFinished` (mot
cible + classement final), `error`

---

## 7. Critères d'acceptation

- [ ] Une partie à 2 joueurs distants se déroule intégralement sans intervention manuelle.
- [ ] Une partie à 4 joueurs sur 4 appareils distincts, rejoints par QR code, se déroule intégralement.
- [ ] Les deux modes de choix du mot (`SYSTEM` et `PLAYER`) sont fonctionnels.
- [ ] Les trois niveaux appliquent bien 10 / 6 / 3 manches.
- [ ] Aucune proposition d'une manche n'est visible avant l'expiration du timer (vérifiable à l'inspection du trafic WebSocket).
- [ ] Le mot cible n'apparaît jamais dans le trafic client avant `gameFinished`.
- [ ] Un mot hors vocabulaire est rejeté avec message explicite, sans consommer la proposition.
- [ ] Deux joueurs proposant le même mot dans une manche marquent tous deux.
- [ ] Deux joueurs à égalité au meilleur pourcentage reçoivent tous deux 50 % de ce pourcentage.
- [ ] Une déconnexion en cours de partie n'interrompt pas la partie ; le joueur peut se reconnecter et retrouver l'historique.
- [ ] Les scores affichés sont des percentiles, avec une distribution visiblement étalée sur l'échelle (vérifier sur une dizaine de propositions de proximité variable).

---

## 8. Hors périmètre (V1)

- Comptes utilisateurs persistants, authentification.
- Classements inter-parties, historique long terme, statistiques.
- Chat textuel ou vocal intégré.
- Modes de jeu additionnels (coopératif, contre-la-montre, somme fixe).
- Internationalisation : **français uniquement** en V1.

---

## 9. Ordre de développement conseillé

1. Script d'élagage hors ligne : téléchargement du modèle, filtrage aux 80 000
   lemmes, production de l'artefact binaire.
2. `semantic-api` seul, testable en ligne de commande : chargement de l'artefact,
   percentiles, validation lexicale. **Valider la qualité du ressenti sémantique
   avant toute autre chose** — si les voisinages sont mauvais, le reste ne sert à rien.
3. `game-api` avec une partie mono-manche, deux joueurs, sans interface soignée.
4. Boucle de manches complète, timer, scoring, gestion des égalités.
5. Interface : vue chronologique, puis vue classement.
6. Salons, QR code, reconnexion.
7. PWA, déploiement.
