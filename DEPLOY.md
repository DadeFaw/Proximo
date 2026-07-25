# Déployer Proximo pour des joueurs à distance

Objectif : une **URL publique HTTPS** que n'importe qui peut ouvrir sur son
téléphone, où qu'il soit. Le jeu a besoin d'un **serveur Python vivant**
(WebSocket + moteur sémantique) : GitHub Pages ne suffit pas, il faut un
hébergeur qui exécute le conteneur Docker. Ce dépôt est prêt pour ça
(`Dockerfile` tout-en-un + `render.yaml`).

---

## Étape 1 — Mettre le code sur GitHub

Le dépôt git local est déjà initialisé et committé. Il reste à créer le dépôt
distant et à pousser.

1. Créez un dépôt vide sur https://github.com/new
   (nom au choix, ex. `proximo` ; **sans** README ni .gitignore, ils existent déjà).
2. Dans PowerShell, à la racine du projet :

   ```powershell
   git remote add origin https://github.com/<votre-compte>/proximo.git
   git branch -M main
   git push -u origin main
   ```

   Au push, GitHub demandera de vous authentifier (navigateur ou *Personal Access
   Token*). Si `git` ne propose rien, installez GitHub CLI (`winget install GitHub.cli`),
   faites `gh auth login`, puis `git push`.

---

## Étape 2 — Déployer sur Render (recommandé, gratuit)

Render lit le `render.yaml` et construit tout automatiquement.

1. Créez un compte sur https://render.com (connexion avec GitHub).
2. **New +** → **Blueprint**.
3. Sélectionnez votre dépôt `proximo` → **Apply**.
4. Render construit l'image (~5–8 min la 1re fois : installe le modèle français,
   pré-calcule le cache) puis publie une URL du type
   **`https://proximo-xxxx.onrender.com`**.
5. Testez : ouvrez l'URL, créez une partie. Partagez l'URL (ou le **QR** du lobby)
   aux joueurs distants — chacun ouvre l'adresse sur son téléphone et rejoint.

C'est tout : l'URL est permanente, en HTTPS (donc PWA installable + QR scannables).

### À savoir sur le plan gratuit Render

- **Mise en veille** après 15 min sans trafic → le 1er accès suivant prend ~30–60 s
  (réveil + chargement du moteur). Pendant une partie active, pas de veille.
- **512 Mo de RAM.** Le conteneur vise ~350–450 Mo. Si vous voyez des erreurs
  « Out of memory » dans les logs Render, passez le service en plan **Starter**
  (toujours actif) ou **Standard** (2 Go) : `plan: standard` dans `render.yaml`.
- Store **en mémoire** : une seule instance. Ne pas activer plusieurs instances
  (l'état de partie ne serait pas partagé). Pour scaler horizontalement, ajoutez
  un service Redis et l'variable `REDIS_URL` (voir plus bas).

---

## Alternatives d'hébergement

Le même `Dockerfile` fonctionne partout. En résumé :

| Hébergeur | Mise en place | Notes |
|---|---|---|
| **Render** | Blueprint (`render.yaml`) | Le plus simple ; détaillé ci-dessus. |
| **Railway** | New Project → Deploy from GitHub repo (détecte le Dockerfile) | ~5 $ de crédit offert, pas de mise en veille, RAM ajustable. Le port est fourni via `$PORT`. |
| **Fly.io** | `fly launch` (CLI) → détecte le Dockerfile | WebSockets natifs ; réglez `memory = 512`/`1024` Mo. |
| **VPS + Docker** | `docker compose up -d` (fichier fourni) + reverse-proxy HTTPS (Caddy/Traefik) | Contrôle total ; met à disposition Redis facilement. |

Sur Railway/Fly, définissez au besoin `PUBLIC_BASE_URL=https://votre-domaine`
si les QR ne pointent pas déjà sur la bonne adresse.

---

## Passer à Redis (multi-instances / persistance)

Le `docker-compose.yml` inclut déjà Redis. En PaaS, ajoutez une base Redis gérée
et définissez sur le service la variable :

```
REDIS_URL=redis://:<mot-de-passe>@<hôte>:<port>/0
```

L'état de partie (TTL 24 h) devient partagé et survit aux redémarrages.

---

## Récapitulatif des variables d'environnement utiles

| Variable | Défaut | Rôle |
|---|---|---|
| `PORT` | fourni par l'hébergeur | Port public du game-api |
| `SEMANTIC_API_URL` | `http://127.0.0.1:8100` | Localisation du semantic-api (interne au conteneur) |
| `REDIS_URL` | — (mémoire) | Active le store Redis partagé |
| `ROUND_SECONDS` | `25` | Durée d'une manche |
| `PUBLIC_BASE_URL` | déduit de la requête | Base des QR / liens de salon |
| `SPACY_MODEL` | `fr_core_news_md` | `fr_core_news_lg` pour ~80 k mots (plus de RAM) |
