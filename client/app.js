import {
  html, render, useState, useEffect, useRef, useMemo,
} from '/vendor/preact-standalone.module.js';

/* ------------------------------------------------------------------ utils */
const LEVELS = {
  FACILE: { rounds: 10, desc: 'concret, très courant' },
  NORMAL: { rounds: 6, desc: 'courant, semi-abstrait' },
  DIFFICILE: { rounds: 3, desc: 'abstrait, rare' },
};
const SKEY = 'proximo:session';

const loadSession = () => {
  try { return JSON.parse(localStorage.getItem(SKEY) || 'null'); } catch { return null; }
};
const saveSession = (s) => localStorage.setItem(SKEY, JSON.stringify(s));
const clearSession = () => localStorage.removeItem(SKEY);

async function api(path, opts) {
  const r = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...opts });
  if (!r.ok) {
    let msg = `Erreur ${r.status}`;
    try { msg = (await r.json()).detail || msg; } catch {}
    throw new Error(msg);
  }
  return r.json();
}

function pctColor(pct, isTarget) {
  if (isTarget) return 'var(--green)';
  const hue = 210 - (Math.max(0, Math.min(100, pct)) / 100) * 195; // froid -> chaud
  return `hsl(${hue.toFixed(0)}, 82%, 55%)`;
}
const fmtScore = (s) => (Number.isInteger(s) ? String(s) : s.toFixed(2).replace(/0+$/, '').replace(/\.$/, ''));
const medal = (rank) => (rank === 1 ? '🥇' : rank === 2 ? '🥈' : rank === 3 ? '🥉' : '');

/* --------------------------------------------------------------- composants */
function PercentileBar({ pct, isTarget }) {
  return html`<div class="bar"><div style=${{ width: `${Math.max(2, pct)}%`, background: pctColor(pct, isTarget) }}></div></div>`;
}

function EntryRow({ e, youId }) {
  const you = e.playerId === youId;
  return html`
    <div class=${'entry' + (e.isTarget ? ' win' : '')}>
      <div class="top">
        <span class="who">${e.pseudo}${you ? ' (toi)' : ''} · <span class="word">${e.word}</span></span>
        <span class="pct" style=${{ color: pctColor(e.percentile, e.isTarget) }}>
          ${e.percentile.toFixed(1)}%${e.roundPoints ? html`<span class="pts">+${fmtScore(e.roundPoints)}</span>` : ''}
        </span>
      </div>
      <${PercentileBar} pct=${e.percentile} isTarget=${e.isTarget} />
    </div>`;
}

function Ranking({ ranking, youId }) {
  if (!ranking || !ranking.length) return html`<p class="muted small">Aucun score pour l'instant.</p>`;
  return html`<ol class="rank">${ranking.map((p) => html`
    <li class=${'p' + p.rank} key=${p.playerId}>
      <span class="pos">${medal(p.rank) || p.rank}</span>
      <div>
        <div class="name">${p.pseudo}${p.playerId === youId ? ' · toi' : ''}</div>
        <div class="sub">${p.connected ? 'connecté' : 'déconnecté'}</div>
      </div>
      <div class="score">${fmtScore(p.score)}<small> pt${p.score >= 2 ? 's' : ''}</small></div>
    </li>`)}</ol>`;
}

function ChronoView({ history, youId }) {
  const rounds = useMemo(() => {
    const by = new Map();
    (history || []).forEach((h) => { if (!by.has(h.round)) by.set(h.round, []); by.get(h.round).push(h); });
    return [...by.entries()].sort((a, b) => b[0] - a[0]); // manches récentes en tête
  }, [history]);
  if (!rounds.length) return html`<p class="muted small">Aucune manche révélée pour l'instant.</p>`;
  return html`<div>${rounds.map(([r, items]) => html`
    <div class="chrono-round" key=${r}>
      <div class="rt"><span>Manche ${r}</span><span>${items.length} proposition${items.length > 1 ? 's' : ''}</span></div>
      ${[...items].sort((a, b) => b.percentile - a.percentile).map((e) => html`<${EntryRow} e=${e} youId=${youId} />`)}
    </div>`)}</div>`;
}

function Timer({ deadline, duration }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 100);
    return () => clearInterval(id);
  }, [deadline]);
  const remaining = Math.max(0, (deadline - now) / 1000);
  const frac = duration ? Math.max(0, Math.min(1, remaining / duration)) : 0;
  return html`
    <div>
      <div class=${'timernum' + (remaining <= 5 ? ' low' : '')}>${remaining.toFixed(1)}s</div>
      <div class="timerbar"><div style=${{ width: `${frac * 100}%` }}></div></div>
    </div>`;
}

/* ------------------------------------------------------------------ écrans */
function Home({ prefillCode, onCreate, onJoin, error, themes }) {
  const [pseudo, setPseudo] = useState(localStorage.getItem('proximo:pseudo') || '');
  const [mode, setMode] = useState('SYSTEM');
  const [level, setLevel] = useState('FACILE');
  const [theme, setTheme] = useState('ALEATOIRE');
  const [code, setCode] = useState(prefillCode || '');
  useEffect(() => { if (prefillCode) setCode(prefillCode); }, [prefillCode]);
  const remember = (p) => { setPseudo(p); localStorage.setItem('proximo:pseudo', p); };

  return html`
    <div class="card">
      <label>Ton pseudo</label>
      <input type="text" value=${pseudo} maxlength="24" placeholder="ex. Camille"
             onInput=${(e) => remember(e.target.value)} />
    </div>

    <div class="card">
      <h2>Créer une partie</h2>
      <label>Qui choisit le mot cible ?</label>
      <div class="seg">
        <button class=${mode === 'SYSTEM' ? 'active' : ''} onClick=${() => setMode('SYSTEM')}>
          Le système<small>tirage au hasard, tous devinent</small></button>
        <button class=${mode === 'PLAYER' ? 'active' : ''} onClick=${() => setMode('PLAYER')}>
          Un joueur<small>l'hôte saisit le mot</small></button>
      </div>
      ${mode === 'SYSTEM' ? html`
        <label>Thème du mot cible</label>
        <div class="seg" style="gap:6px">
          ${(themes && themes.length ? themes : [{ key: 'ALEATOIRE', label: 'Aléatoire', emoji: '🎲' }]).map((t) => html`
            <button key=${t.key} class=${theme === t.key ? 'active' : ''}
                    style="flex:0 0 auto;min-width:auto;padding:8px 12px;font-size:13px"
                    onClick=${() => setTheme(t.key)}>${t.emoji} ${t.label}</button>`)}
        </div>` : ''}
      <label>Niveau</label>
      <div class="seg">
        ${Object.entries(LEVELS).map(([k, v]) => html`
          <button class=${level === k ? 'active' : ''} onClick=${() => setLevel(k)}>
            ${k[0] + k.slice(1).toLowerCase()}<small>${v.rounds} manches</small></button>`)}
      </div>
      <button class="btn" disabled=${!pseudo.trim()}
              onClick=${() => onCreate({ mode, level, theme: mode === 'SYSTEM' ? theme : null, pseudo: pseudo.trim() })}>
        Créer le salon →</button>
    </div>

    <div class="divider">— ou —</div>

    <div class="card">
      <h2>Rejoindre une partie</h2>
      <label>Code du salon</label>
      <input type="text" value=${code} maxlength="6" placeholder="6 caractères"
             style="text-transform:uppercase;letter-spacing:4px;font-size:20px;text-align:center"
             onInput=${(e) => setCode(e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, ''))} />
      <button class="btn ghost" disabled=${!pseudo.trim() || code.length < 6}
              onClick=${() => onJoin({ code, pseudo: pseudo.trim() })}>Rejoindre</button>
    </div>
    ${error ? html`<p class="err center">${error}</p>` : ''}
  `;
}

function Lobby({ st, code, youId, isHost, send, onLeave, themes }) {
  const [target, setTarget] = useState('');
  const players = st.players || [];
  const canStart = players.length >= 2 && (st.mode === 'SYSTEM' || st.hasTarget);
  const meSetter = st.mode === 'PLAYER' && isHost;
  const joinUrl = `${location.origin}/?code=${code}`;
  const themeInfo = (themes || []).find((t) => t.key === st.theme);

  return html`
    <div class="card center">
      <div class="muted small">Code du salon — partage-le ou scanne le QR</div>
      <div class="code">${code}</div>
      <div class="qr"><img src=${`/api/rooms/${code}/qr.svg`} alt="QR du salon" /></div>
      <div class="copyrow" style="margin-top:12px">
        <input type="text" readonly value=${joinUrl} onClick=${(e) => e.target.select()} />
        <button class="btn ghost" style="margin:0;width:auto;padding:12px 14px"
                onClick=${() => navigator.clipboard?.writeText(joinUrl)}>Copier</button>
      </div>
    </div>

    <div class="card">
      <h2>Joueurs (${players.length})</h2>
      <div class="muted small">Mode ${st.mode === 'SYSTEM' ? 'système' : 'joueur'} · niveau ${st.level?.toLowerCase()} · ${st.totalRounds} manches${st.mode === 'SYSTEM' && themeInfo && themeInfo.key !== 'ALEATOIRE' ? ` · thème ${themeInfo.emoji} ${themeInfo.label}` : ''}</div>
      <ul class="players">${players.map((p) => html`
        <li key=${p.id}>
          <span class=${'dot' + (p.connected ? '' : ' off')}></span>
          <span>${p.pseudo}</span>
          ${p.id === youId ? html`<span class="pill you">toi</span>` : ''}
          ${p.isHost ? html`<span class="pill host">hôte</span>` : ''}
          ${p.isSetter ? html`<span class="pill setter">maître du mot</span>` : ''}
        </li>`)}</ul>
    </div>

    ${meSetter ? html`
      <div class="card">
        <h2>Ton mot cible</h2>
        <p class="muted small">Tu ne devineras pas cette manche. Le mot est validé avant le lancement (nom commun, connu du dictionnaire).</p>
        ${st.hasTarget ? html`<div class="banner">Mot cible défini ✓ — tu peux lancer la partie.</div>` : ''}
        <input type="text" value=${target} placeholder="ex. horizon"
               onInput=${(e) => setTarget(e.target.value)} />
        <button class="btn amber" disabled=${!target.trim()}
                onClick=${() => { send('setTargetWord', { word: target.trim() }); setTarget(''); }}>
          Valider le mot cible</button>
      </div>` : ''}

    ${isHost ? html`
      <button class="btn" disabled=${!canStart} onClick=${() => send('startGame', {})}>
        ${canStart ? 'Lancer la partie' : (players.length < 2 ? 'En attente d\'un 2ᵉ joueur…' : 'Définis d\'abord le mot cible')}
      </button>` : html`<div class="waiting">En attente du lancement par l'hôte…</div>`}

    <button class="btn ghost" onClick=${onLeave}>Quitter</button>
  `;
}

function RoundView({ st, roundInfo, youId, myGuess, send }) {
  const [word, setWord] = useState('');
  useEffect(() => { setWord(''); }, [roundInfo?.round]);
  const isSetter = st.wordSetterId === youId;
  const submitted = myGuess?.submitted;
  const submit = () => { if (word.trim()) send('submitGuess', { word: word.trim() }); };

  return html`
    <div class="card">
      <div class="roundhead">
        <strong>Manche ${roundInfo?.round} / ${roundInfo?.totalRounds}</strong>
        <span class="r">trouve le mot cible</span>
      </div>
      ${roundInfo?.deadline ? html`<${Timer} deadline=${roundInfo.deadline} duration=${roundInfo.durationSeconds} />` : ''}
    </div>

    <div class="card">
      ${isSetter ? html`
        <div class="waiting"><div class="spinner"></div>Tu es le maître du mot.<br/>Les autres cherchent ton mot…</div>`
      : submitted ? html`
        <div class="banner">Proposition envoyée : <b>${myGuess.word}</b></div>
        <div class="waiting"><div class="spinner"></div>En attente des autres joueurs…<br/>
          <span class="small">Scores révélés à la fin du chrono, simultanément.</span></div>`
      : html`
        <label>Ta proposition (une seule par manche)</label>
        <input type="text" value=${word} autofocus placeholder="tape un mot…"
               onInput=${(e) => setWord(e.target.value)}
               onKeyDown=${(e) => e.key === 'Enter' && submit()} />
        <button class="btn" disabled=${!word.trim()} onClick=${submit}>Proposer</button>
        <p class="muted small">Un mot inconnu du dictionnaire est refusé sans consommer ton tour.</p>`}
    </div>

    <div class="card">
      <h2>Joueurs</h2>
      <ul class="players">${(st.players || []).map((p) => html`
        <li key=${p.id}>
          <span class=${'dot' + (p.connected ? '' : ' off')}></span>
          <span>${p.pseudo}${p.id === youId ? ' · toi' : ''}</span>
          ${p.isSetter ? html`<span class="pill setter">maître du mot</span>` : ''}
        </li>`)}</ul>
      <p class="muted small">🏆 Le classement et les points sont dévoilés à la fin de la partie.</p>
    </div>
  `;
}

function RevealView({ reveal, youId, isHost, send }) {
  const over = reveal.gameOver;
  return html`
    <div class="card">
      <div class="roundhead"><strong>Manche ${reveal.round} / ${reveal.totalRounds} — révélation</strong>
        ${reveal.hasWinner ? html`<span class="r" style="color:var(--green)">cible trouvée ! 🎯</span>` : ''}</div>
      <p class="muted small">Toutes les propositions et leur proximité sémantique avec le mot cible :</p>
      ${reveal.entries.length ? reveal.entries.map((e) => html`<${EntryRow} e=${e} youId=${youId} />`)
        : html`<p class="muted">Personne n'a proposé cette manche.</p>`}
    </div>
    ${isHost
      ? html`<button class=${'btn' + (over ? ' amber' : '')} onClick=${() => send('nextRound', {})}>
          ${over ? '🏆 Voir les résultats' : 'Manche suivante →'}</button>`
      : html`<div class="waiting"><div class="spinner"></div>
          En attente que l'hôte ${over ? 'dévoile les résultats' : 'lance la manche suivante'}…</div>`}
  `;
}

function Finished({ finished, youId, onLeave }) {
  const [tab, setTab] = useState('classement');
  return html`
    <div class="card center">
      <div class="target">Le mot cible était<b>${finished.targetWord}</b></div>
    </div>
    <div class="tabs">
      <button class=${tab === 'classement' ? 'active' : ''} onClick=${() => setTab('classement')}>Classement</button>
      <button class=${tab === 'chrono' ? 'active' : ''} onClick=${() => setTab('chrono')}>Chronologique</button>
    </div>
    <div class="card">
      ${tab === 'classement'
        ? html`<${Ranking} ranking=${finished.ranking} youId=${youId} />`
        : html`<${ChronoView} history=${finished.history} youId=${youId} />`}
    </div>
    <button class="btn" onClick=${onLeave}>Nouvelle partie</button>
  `;
}

/* --------------------------------------------------------------------- app */
function App() {
  const [screen, setScreen] = useState('home');
  const [session, setSession] = useState(null);          // {code, playerId, pseudo, isHost}
  const [st, setSt] = useState({ players: [], ranking: [], history: [] });
  const [roundInfo, setRoundInfo] = useState(null);
  const [reveal, setReveal] = useState(null);
  const [finished, setFinished] = useState(null);
  const [myGuess, setMyGuess] = useState(null);
  const [toast, setToast] = useState(null);
  const [homeErr, setHomeErr] = useState('');
  const [gameTab, setGameTab] = useState('classement');
  const [themes, setThemes] = useState([]);

  const ws = useRef(null);
  const intentional = useRef(false);
  const sessRef = useRef(null);
  const prefillCode = useMemo(() => new URLSearchParams(location.search).get('code') || '', []);

  const flash = (msg, type = 'error') => { setToast({ msg, type }); setTimeout(() => setToast(null), 3200); };

  function handle(m) {
    switch (m.type) {
      case 'joined': {
        setSession((s) => { const ns = { ...(s || sessRef.current), playerId: m.playerId, isHost: m.isHost }; sessRef.current = ns; saveSession(ns); return ns; });
        break;
      }
      case 'state': setSt((prev) => ({ ...prev, ...m.state })); if (m.state.status === 'RUNNING' && m.state.roundDeadline) setRoundInfo({ round: m.state.currentRound, totalRounds: m.state.totalRounds, deadline: m.state.roundDeadline, durationSeconds: 25 }); break;
      case 'lobbyUpdate': setSt((prev) => ({ ...prev, ...m })); break;
      case 'gameStarted': setSt((prev) => ({ ...prev, status: 'RUNNING', totalRounds: m.totalRounds, level: m.level, mode: m.mode })); setReveal(null); setFinished(null); setMyGuess(null); break;
      case 'roundStarted': setRoundInfo({ round: m.round, totalRounds: m.totalRounds, deadline: m.deadline, durationSeconds: m.durationSeconds }); setSt((prev) => ({ ...prev, status: 'RUNNING', currentRound: m.round })); setReveal(null); setMyGuess(null); break;
      case 'guessAccepted': setMyGuess({ submitted: true, word: m.word }); break;
      case 'roundRevealed':
        setReveal(m);
        setSt((prev) => ({
          ...prev, status: 'REVEALING', players: m.players || prev.players,
          history: [...(prev.history || []), ...m.entries.map((e) => ({ ...e, round: m.round }))],
        }));
        break;
      case 'gameFinished': setFinished(m); setSt((prev) => ({ ...prev, status: 'FINISHED', targetWord: m.targetWord, ranking: m.ranking, history: m.history })); break;
      case 'targetSet': flash('Mot cible défini ✓', 'info'); break;
      case 'error':
        flash(m.message);
        if (/introuvable|complet|déjà commencé/i.test(m.message)) { setHomeErr(m.message); doLeave(); }
        break;
      default: break;
    }
  }

  function connect(sess) {
    sessRef.current = sess;
    intentional.current = false;
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const sock = new WebSocket(`${proto}://${location.host}/ws/${sess.code}`);
    ws.current = sock;
    sock.onopen = () => sock.send(JSON.stringify({ type: 'join', pseudo: sess.pseudo, playerId: sess.playerId }));
    sock.onmessage = (ev) => { try { handle(JSON.parse(ev.data)); } catch {} };
    sock.onclose = () => {
      if (intentional.current) return;
      if (sessRef.current) setTimeout(() => { if (!intentional.current) connect(sessRef.current); }, 1500);
    };
  }

  function send(type, payload) {
    const s = ws.current;
    if (s && s.readyState === WebSocket.OPEN) s.send(JSON.stringify({ type, ...payload }));
    else flash('Connexion perdue, reconnexion…');
  }

  async function onCreate({ mode, level, theme, pseudo }) {
    setHomeErr('');
    try {
      const { code } = await api('/api/rooms', { method: 'POST', body: JSON.stringify({ mode, level, theme }) });
      const sess = { code, pseudo, playerId: null, isHost: true };
      setSession(sess); setScreen('game'); connect(sess);
    } catch (e) { setHomeErr(e.message); }
  }
  function onJoin({ code, pseudo }) {
    setHomeErr('');
    const sess = { code, pseudo, playerId: null, isHost: false };
    setSession(sess); setScreen('game'); connect(sess);
  }
  function doLeave() {
    intentional.current = true;
    try { ws.current?.close(); } catch {}
    ws.current = null; sessRef.current = null;
    clearSession();
    setSession(null); setScreen('home');
    setSt({ players: [], ranking: [], history: [] });
    setRoundInfo(null); setReveal(null); setFinished(null); setMyGuess(null);
  }

  // Liste des thèmes (pour l'écran d'accueil).
  useEffect(() => {
    fetch('/api/themes').then((r) => r.json()).then((d) => setThemes(d.themes || [])).catch(() => {});
  }, []);

  // Reconnexion automatique au chargement si une session avec playerId existe.
  useEffect(() => {
    const last = loadSession();
    if (last && last.code && last.playerId) {
      setSession(last); setScreen('game'); connect(last);
    }
    return () => { intentional.current = true; try { ws.current?.close(); } catch {} };
  }, []);

  const youId = session?.playerId;
  const isHost = session?.isHost;

  let body;
  if (screen === 'home') {
    body = html`<${Home} prefillCode=${prefillCode} onCreate=${onCreate} onJoin=${onJoin} error=${homeErr} themes=${themes} />`;
  } else if (finished || st.status === 'FINISHED') {
    body = html`<${Finished} finished=${finished || { targetWord: st.targetWord, ranking: st.ranking, history: st.history }} youId=${youId} onLeave=${doLeave} />`;
  } else if (st.status === 'REVEALING' && reveal) {
    body = html`<${RevealView} reveal=${reveal} youId=${youId} isHost=${isHost} send=${send} />`;
  } else if (st.status === 'RUNNING') {
    body = html`<${RoundView} st=${st} roundInfo=${roundInfo} youId=${youId} myGuess=${myGuess} send=${send} />`;
  } else {
    body = html`<${Lobby} st=${st} code=${session?.code} youId=${youId} isHost=${isHost} send=${send} onLeave=${doLeave} themes=${themes} />`;
  }

  return html`
    <div class="wrap">
      <div class="brand">
        <img src="/icons/icon-192.png" alt="" />
        <h1>Proximo</h1>
        <span class="tag">proximité sémantique</span>
      </div>
      ${body}
      ${toast ? html`<div class=${'toast' + (toast.type === 'info' ? ' info' : '')}>${toast.msg}</div>` : ''}
    </div>`;
}

render(html`<${App} />`, document.getElementById('app'));
