"""
Carte Manuelle — version réécrite.

Principe : Streamlit ne fait plus QUE deux choses (réveiller le serveur Render et
injecter l'URL du serveur dans la page). Toute la logique carte (placement,
déplacement, recherche, étapes, reset, recalcul) vit dans le composant HTML.
Aucun widget Streamlit ne déclenche de rerun -> plus de perte d'état, plus de
marqueurs fantômes, plus de reset qui ne reset rien.

Contrat serveur utilisé (identique à l'existant, champs en plus ignorés si non gérés) :
    POST {MAP_SERVER_URL}/api/recalculate
    {
      "origin": "50.630000,5.570000",        # ou "Liège, Belgium"
      "dest":   "51.130000,2.750000",
      "origin_coords": [lat, lon],           # bonus
      "dest_coords":   [lat, lon],           # bonus
      "via":       [[lat, lon], ...],        # étapes intermédiaires
      "waypoints": ["lat,lon", ...],         # même chose, format texte
      "avoid_tolls": false,
      "avoid_highways": false
    }
    -> { polyline, distance_km, duration_h, prix_peage, route_id }
"""

import os
import time
from pathlib import Path

import requests
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

# ─── Config ───────────────────────────────────────────────────────────────────
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")
MAP_SERVER_URL = os.environ.get("MAP_SERVER_URL", "https://hub-m36x.onrender.com").rstrip("/")

st.set_page_config(page_title="Carte Manuelle", page_icon="🗺️", layout="wide")

st.markdown(
    """
    <style>
      .block-container { padding: 0 !important; margin: 0 !important; max-width: 100% !important; }
      header, #MainMenu, footer { display: none !important; }
      section[data-testid="stMain"] > div:first-child { padding: 0 !important; }
      div[data-testid="stVerticalBlock"] { gap: 0 !important; }
      iframe[title="streamlit.components.v1.html"],
      iframe[title="components.html"] {
          display: block !important; border: none !important;
          width: 100% !important; height: calc(100vh - 8px) !important;
      }
    </style>
    """,
    unsafe_allow_html=True,
)


# ─── Réveil du serveur Render (une seule fois, sans boucle de rerun) ──────────
@st.cache_data(ttl=600, show_spinner=False)
def wake_server(url: str) -> bool:
    for _ in range(3):
        try:
            if requests.get(f"{url}/health", timeout=12).status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(4)
    return False


with st.spinner("Réveil du serveur carte…"):
    server_up = wake_server(MAP_SERVER_URL)


# ─── Composant carte ─────────────────────────────────────────────────────────
MAP_HTML = r"""
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600&family=Barlow:wght@400;500;600&display=swap" rel="stylesheet">

<style>
  :root{
    --navy:#001B4D; --navy2:#022A6B; --blue:#0057A8; --blue-l:#2E87E0;
    --ink:#0E1420; --line:#123067; --txt:#E9EEF6; --muted:#93A6C4;
    --ok:#2FA36B; --warn:#D9822B; --err:#C4433B;
  }
  *{box-sizing:border-box;}
  html,body{margin:0;padding:0;height:100%;background:var(--ink);
            font-family:'Barlow',system-ui,sans-serif;color:var(--txt);}
  #app{display:flex;flex-direction:column;height:100vh;}

  /* ── Barre de commande ── */
  .bar{background:var(--navy);border-bottom:2px solid var(--blue);
       display:flex;align-items:center;gap:14px;padding:8px 12px;flex-wrap:wrap;}
  .title{font-family:'Barlow Condensed',sans-serif;font-size:22px;font-weight:600;
         letter-spacing:.5px;color:#fff;white-space:nowrap;}
  .dot{width:8px;height:8px;border-radius:50%;display:inline-block;margin-right:6px;
       background:var(--muted);vertical-align:middle;}
  .dot.up{background:var(--ok);} .dot.down{background:var(--err);}

  .search{position:relative;flex:1 1 320px;min-width:240px;}
  .search input{width:100%;padding:8px 10px;border:1px solid var(--line);
       background:#04152F;color:var(--txt);font-size:14px;border-radius:2px;outline:none;}
  .search input:focus{border-color:var(--blue-l);}
  .results{position:absolute;top:38px;left:0;right:0;background:#04152F;
       border:1px solid var(--line);max-height:280px;overflow:auto;z-index:1200;display:none;}
  .results.show{display:block;}
  .res{display:flex;align-items:center;gap:8px;padding:7px 9px;border-bottom:1px solid #0C2450;
       cursor:pointer;font-size:13px;}
  .res:hover{background:#072047;}
  .res .lbl{flex:1;line-height:1.25;}
  .res .sub{color:var(--muted);font-size:11.5px;}
  .mini{border:1px solid var(--line);background:#0A2352;color:var(--txt);
        font-size:11px;padding:3px 7px;cursor:pointer;border-radius:2px;}
  .mini:hover{background:var(--blue);border-color:var(--blue-l);}

  .grp{display:flex;gap:6px;align-items:center;flex-wrap:wrap;}
  button.act{font-family:'Barlow Condensed',sans-serif;font-size:15px;letter-spacing:.3px;
        background:var(--navy2);color:var(--txt);border:1px solid var(--line);
        padding:7px 11px;cursor:pointer;border-radius:2px;}
  button.act:hover{background:var(--blue);border-color:var(--blue-l);}
  button.act.on{background:var(--blue);border-color:#7FB6F0;color:#fff;}
  button.act.danger:hover{background:var(--err);border-color:#E2746C;}
  button.act:focus-visible{outline:2px solid #7FB6F0;outline-offset:1px;}
  label.chk{font-size:13px;color:var(--txt);display:flex;align-items:center;gap:5px;cursor:pointer;}

  /* ── Bandeau résultats ── */
  .stats{display:flex;gap:0;background:#04152F;border-bottom:1px solid var(--line);}
  .stat{padding:6px 16px;border-right:1px solid var(--line);min-width:120px;}
  .stat .k{font-size:11px;color:var(--muted);}
  .stat .v{font-family:'Barlow Condensed',sans-serif;font-size:19px;font-weight:600;line-height:1.1;}
  .stat.msg{flex:1;border-right:none;display:flex;align-items:center;font-size:13px;color:var(--muted);}
  .stat.msg.err{color:#FF8B82;}
  .stat.msg.busy{color:#7FB6F0;}

  /* ── Carte ── */
  #map{flex:1;background:#0B1220;}
  #map.picking{cursor:crosshair;}
  .leaflet-container{font-family:'Barlow',sans-serif;}
  .pin{width:26px;height:26px;border-radius:50%;border:2px solid #fff;
       display:flex;align-items:center;justify-content:center;
       font-family:'Barlow Condensed',sans-serif;font-size:14px;font-weight:600;color:#fff;
       box-shadow:0 0 0 1px rgba(0,0,0,.35);}
  .pin.start{background:var(--ok);} .pin.end{background:var(--err);} .pin.via{background:var(--blue);}
  .pop{font-size:13px;min-width:170px;}
  .pop b{font-family:'Barlow Condensed',sans-serif;font-size:15px;}
  .pop .co{color:#5A6B87;font-size:11.5px;margin:3px 0 7px;}
  .pop button{width:100%;margin-top:4px;padding:5px;border:1px solid #C9D5E6;background:#F3F6FB;
              cursor:pointer;font-size:12.5px;border-radius:2px;}
  .pop button:hover{background:#E3EBF6;}
  .hint{position:absolute;bottom:14px;left:50%;transform:translateX(-50%);z-index:1100;
        background:var(--navy);border:1px solid var(--blue);padding:6px 14px;font-size:13px;
        border-radius:2px;display:none;}
  .hint.show{display:block;}
  @media (prefers-reduced-motion:no-preference){ .hint.show{animation:none;} }
</style>

<div id="app">
  <div class="bar">
    <div class="title"><span id="srv" class="dot"></span>Carte manuelle</div>

    <div class="search">
      <input id="q" type="text" autocomplete="off" placeholder="Chercher une ville, une adresse, un code postal">
      <div id="res" class="results"></div>
    </div>

    <div class="grp">
      <button class="act" data-mode="start">Placer le départ</button>
      <button class="act" data-mode="end">Placer l'arrivée</button>
      <button class="act" data-mode="via">Ajouter une étape</button>
      <button class="act" id="swap">Inverser</button>
      <button class="act" id="fit">Cadrer</button>
      <button class="act danger" id="reset">Tout effacer</button>
    </div>

    <div class="grp">
      <label class="chk"><input type="checkbox" id="tolls"> Éviter les péages</label>
      <label class="chk"><input type="checkbox" id="hw"> Éviter les autoroutes</label>
    </div>
  </div>

  <div class="stats">
    <div class="stat"><div class="k">Distance</div><div class="v" id="s-km">—</div></div>
    <div class="stat"><div class="k">Durée</div><div class="v" id="s-h">—</div></div>
    <div class="stat"><div class="k">Péages</div><div class="v" id="s-p">—</div></div>
    <div class="stat"><div class="k">Étapes</div><div class="v" id="s-v">0</div></div>
    <div class="stat msg" id="s-msg">Cliquez sur la carte pour poser le départ, puis l'arrivée.</div>
  </div>

  <div id="map"></div>
  <div id="hint" class="hint"></div>
</div>

<script>
(function(){
  const SERVER = "__SERVER_URL__".replace(/\/+$/,"");
  const HOME = [50.55, 5.40], HOME_Z = 7;

  const $ = id => document.getElementById(id);

  /* ── état unique ── */
  const S = { start:null, end:null, vias:[], tolls:false, hw:false, route:null };
  const M = { start:null, end:null, vias:[] };
  let line = null, casing = null, ghost = null;
  let mode = null, timer = null, ctrl = null;

  /* ── carte ── */
  const map = L.map('map', { zoomControl:true }).setView(HOME, HOME_Z);
  L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png',
    { maxZoom:19, subdomains:'abcd',
      attribution:'&copy; OpenStreetMap, &copy; CARTO' }).addTo(map);

  const fmt = p => p.lat.toFixed(6) + "," + p.lng.toFixed(6);

  /* ── messages ── */
  function msg(text, kind){
    const el = $('s-msg');
    el.className = 'stat msg' + (kind ? ' ' + kind : '');
    el.textContent = text;
  }
  let hintT = null;
  function hint(text){
    const el = $('hint');
    el.textContent = text; el.classList.add('show');
    clearTimeout(hintT); hintT = setTimeout(()=>el.classList.remove('show'), 2200);
  }

  /* ── marqueurs : on redessine tout à chaque changement, jamais de patch partiel ── */
  function icon(kind, label){
    return L.divIcon({ className:'', iconSize:[26,26], iconAnchor:[13,13], popupAnchor:[0,-12],
                       html:'<div class="pin '+kind+'">'+label+'</div>' });
  }

  function popup(kind, idx, latlng){
    const d = document.createElement('div');
    d.className = 'pop';
    const names = { start:'Départ', end:'Arrivée', via:'Étape ' + (idx+1) };
    d.innerHTML = '<b>'+names[kind]+'</b><div class="co">'+fmt(latlng)+'</div>';
    const del = document.createElement('button');
    del.textContent = 'Supprimer ce point';
    del.onclick = () => { remove(kind, idx); map.closePopup(); };
    d.appendChild(del);
    if (kind === 'via'){
      const up = document.createElement('button');
      up.textContent = 'Faire passer en premier';
      up.onclick = () => { const v = S.vias.splice(idx,1)[0]; S.vias.unshift(v);
                           map.closePopup(); redraw(); go(); };
      d.appendChild(up);
    }
    return d;
  }

  function marker(kind, latlng, label, idx){
    const m = L.marker(latlng, { draggable:true, autoPan:true, icon:icon(kind,label) }).addTo(map);
    m.on('dragstart', () => { if (ctrl) ctrl.abort(); });
    m.on('drag', e => ghostLine());
    m.on('dragend', e => {
      const p = e.target.getLatLng();
      if (kind === 'via') S.vias[idx] = p; else S[kind] = p;
      go();
    });
    m.bindPopup(() => popup(kind, idx, m.getLatLng()));
    return m;
  }

  function redraw(){
    [M.start, M.end].forEach(m => { if (m) map.removeLayer(m); });
    M.vias.forEach(m => map.removeLayer(m));
    M.start = M.end = null; M.vias = [];
    if (S.start) M.start = marker('start', S.start, 'D');
    if (S.end)   M.end   = marker('end',   S.end,   'A');
    S.vias.forEach((v,i) => M.vias.push(marker('via', v, String(i+1), i)));
    $('s-v').textContent = S.vias.length;
    save();
  }

  function place(kind, latlng){
    if (kind === 'via') S.vias.push(latlng); else S[kind] = latlng;
    redraw(); go();
  }

  function remove(kind, idx){
    if (kind === 'via') S.vias.splice(idx,1); else S[kind] = null;
    redraw(); go();
  }

  /* ── tracé ── */
  function clearLine(){
    [casing, line, ghost].forEach(l => { if (l) map.removeLayer(l); });
    casing = line = ghost = null;
  }

  function ghostLine(){
    const live = [];
    if (M.start) live.push(M.start.getLatLng());
    M.vias.forEach(m => live.push(m.getLatLng()));
    if (M.end) live.push(M.end.getLatLng());
    if (ghost) map.removeLayer(ghost);
    if (live.length < 2) return;
    ghost = L.polyline(live, { color:'#7FB6F0', weight:2, dashArray:'5,6', opacity:.9 }).addTo(map);
  }

  function drawRoute(pts){
    clearLine();
    if (!pts || pts.length < 2) return;
    casing = L.polyline(pts, { color:'#001B4D', weight:10, opacity:.95 }).addTo(map);
    line   = L.polyline(pts, { color:'#0057A8', weight:6,  opacity:1 }).addTo(map);
    line.on('click', e => { L.DomEvent.stop(e); insertOnRoute(e.latlng); });
    line.bindTooltip('Cliquez sur le tracé pour insérer une étape', { sticky:true, direction:'top' });
  }

  function nearestIdx(pts, p){
    let best = 0, bd = Infinity;
    for (let i=0;i<pts.length;i++){
      const d = map.distance(pts[i], p);
      if (d < bd){ bd = d; best = i; }
    }
    return best;
  }

  function insertOnRoute(latlng){
    if (!line){ place('via', latlng); return; }
    const pts = line.getLatLngs();
    const i = nearestIdx(pts, latlng);
    const order = S.vias.map(v => nearestIdx(pts, v));
    let pos = order.findIndex(o => o > i);
    if (pos < 0) pos = S.vias.length;
    S.vias.splice(pos, 0, latlng);
    redraw(); go();
    hint('Étape insérée');
  }

  /* ── polyline : accepte [[lat,lng]], [{lat,lng|lon}], ou chaîne encodée ── */
  function toPts(poly){
    if (!poly) return [];
    if (typeof poly === 'string') return decode(poly);
    if (!Array.isArray(poly) || !poly.length) return [];
    const f = poly[0];
    if (Array.isArray(f)){
      const latFirst = Math.abs(f[0]) <= 90 && (Math.abs(f[1]) > 90 || Math.abs(f[0]) <= 71);
      return poly.map(p => latFirst ? [p[0], p[1]] : [p[1], p[0]]);
    }
    if (typeof f === 'object'){
      return poly.map(p => [ p.lat ?? p.latitude ?? p.y, p.lng ?? p.lon ?? p.longitude ?? p.x ]);
    }
    return [];
  }

  function decode(str){
    let i=0, lat=0, lng=0; const out=[];
    while (i < str.length){
      let b, sh=0, r=0;
      do { b = str.charCodeAt(i++)-63; r |= (b & 0x1f) << sh; sh += 5; } while (b >= 0x20);
      lat += (r & 1) ? ~(r >> 1) : (r >> 1);
      sh = 0; r = 0;
      do { b = str.charCodeAt(i++)-63; r |= (b & 0x1f) << sh; sh += 5; } while (b >= 0x20);
      lng += (r & 1) ? ~(r >> 1) : (r >> 1);
      out.push([lat/1e5, lng/1e5]);
    }
    return out;
  }

  /* ── recalcul ── */
  function go(){ clearTimeout(timer); timer = setTimeout(recalc, 250); }

  async function recalc(){
    if (!S.start || !S.end){
      clearLine(); stats(null);
      msg(!S.start ? 'Posez le point de départ.' : 'Posez le point d\'arrivée.');
      save(); return;
    }
    if (ctrl) ctrl.abort();
    ctrl = new AbortController();
    msg('Calcul de l\'itinéraire…', 'busy');
    ghostLine();

    const body = {
      origin: fmt(S.start), dest: fmt(S.end),
      origin_coords: [S.start.lat, S.start.lng],
      dest_coords:   [S.end.lat,   S.end.lng],
      via:       S.vias.map(v => [v.lat, v.lng]),
      waypoints: S.vias.map(fmt),
      avoid_tolls: S.tolls, avoid_highways: S.hw
    };

    try{
      const r = await fetch(SERVER + '/api/recalculate', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify(body), signal: ctrl.signal
      });
      if (!r.ok){
        const t = await r.text();
        throw new Error('Serveur ' + r.status + ' — ' + t.slice(0,140));
      }
      const data = await r.json();
      const pts = toPts(data.polyline || data.geometry || data.points);
      if (!pts.length) throw new Error('Le serveur n\'a renvoyé aucun tracé.');
      S.route = data;
      drawRoute(pts);
      stats(data);
      msg('Itinéraire à jour. Déplacez un point pour recalculer.');
      save();
    } catch(err){
      if (err.name === 'AbortError') return;
      msg(err.message, 'err');
    }
  }

  function stats(d){
    if (!d){ $('s-km').textContent = '—'; $('s-h').textContent = '—'; $('s-p').textContent = '—'; return; }
    const km = parseFloat(d.distance_km);
    $('s-km').textContent = isNaN(km) ? (d.distance_km || '—') : km.toFixed(0) + ' km';
    const h = parseFloat(d.duration_h);
    $('s-h').textContent = isNaN(h) ? (d.duration_h || '—')
      : Math.floor(h) + ' h ' + String(Math.round((h % 1) * 60)).padStart(2,'0');
    const p = parseFloat(d.prix_peage);
    $('s-p').textContent = isNaN(p) ? '—' : p.toFixed(2).replace('.', ',') + ' €';
  }

  /* ── interactions carte ── */
  function setMode(m){
    mode = m;
    document.querySelectorAll('[data-mode]').forEach(b => b.classList.toggle('on', b.dataset.mode === m));
    $('map').classList.toggle('picking', !!m);
    if (m) hint(m === 'start' ? 'Cliquez sur la carte pour poser le départ'
              : m === 'end'   ? 'Cliquez sur la carte pour poser l\'arrivée'
                              : 'Cliquez sur la carte pour ajouter une étape');
  }

  map.on('click', e => {
    if (mode){ place(mode, e.latlng); setMode(null); return; }
    if (!S.start){ place('start', e.latlng); hint('Départ posé'); return; }
    if (!S.end){ place('end', e.latlng); hint('Arrivée posée'); return; }
  });

  map.on('contextmenu', e => {
    const d = document.createElement('div');
    d.className = 'pop';
    d.innerHTML = '<b>Ce point</b><div class="co">' + fmt(e.latlng) + '</div>';
    [['Définir comme départ','start'], ['Définir comme arrivée','end'], ['Ajouter comme étape','via']]
      .forEach(([txt, kind]) => {
        const b = document.createElement('button');
        b.textContent = txt;
        b.onclick = () => { place(kind, e.latlng); map.closePopup(); };
        d.appendChild(b);
      });
    L.popup({ closeButton:true }).setLatLng(e.latlng).setContent(d).openOn(map);
  });

  /* ── boutons ── */
  document.querySelectorAll('[data-mode]').forEach(b => {
    b.onclick = () => setMode(mode === b.dataset.mode ? null : b.dataset.mode);
  });

  $('fit').onclick = () => {
    const pts = line ? line.getLatLngs() : [S.start, ...S.vias, S.end].filter(Boolean);
    if (!pts.length){ map.setView(HOME, HOME_Z); return; }
    map.fitBounds(L.latLngBounds(pts), { padding:[45,45] });
  };

  $('swap').onclick = () => {
    if (!S.start && !S.end) return;
    const a = S.start; S.start = S.end; S.end = a;
    S.vias.reverse();
    redraw(); go(); hint('Départ et arrivée inversés');
  };

  $('reset').onclick = () => {
    if (ctrl) ctrl.abort();
    clearTimeout(timer);
    S.start = S.end = null; S.vias = []; S.route = null;
    setMode(null);
    clearLine(); redraw(); stats(null);
    $('q').value = ''; $('res').classList.remove('show'); $('res').innerHTML = '';
    map.closePopup();
    map.setView(HOME, HOME_Z);
    msg('Carte vidée. Cliquez pour poser le départ, puis l\'arrivée.');
    save();
  };

  $('tolls').onchange = e => { S.tolls = e.target.checked; go(); };
  $('hw').onchange    = e => { S.hw    = e.target.checked; go(); };

  /* ── recherche (Photon / Komoot, CORS ouvert) ── */
  const box = $('q'), list = $('res');
  let sT = null, hits = [];

  box.addEventListener('input', () => {
    clearTimeout(sT);
    const q = box.value.trim();
    if (q.length < 3){ list.classList.remove('show'); return; }
    sT = setTimeout(() => search(q), 320);
  });

  box.addEventListener('keydown', e => {
    if (e.key === 'Enter' && hits.length){
      e.preventDefault();
      const next = !S.start ? 'start' : (!S.end ? 'end' : 'via');
      pick(hits[0], next);
    }
    if (e.key === 'Escape') list.classList.remove('show');
  });

  document.addEventListener('click', e => {
    if (!e.target.closest('.search')) list.classList.remove('show');
  });

  async function search(q){
    try{
      const url = 'https://photon.komoot.io/api/?lang=fr&limit=6&q=' + encodeURIComponent(q);
      const r = await fetch(url);
      const j = await r.json();
      hits = (j.features || []).map(f => ({
        lat: f.geometry.coordinates[1], lng: f.geometry.coordinates[0], p: f.properties || {}
      }));
      render();
    } catch(err){
      list.innerHTML = '<div class="res"><span class="lbl">Recherche indisponible</span></div>';
      list.classList.add('show');
    }
  }

  function labelOf(p){
    const head = [p.name, p.street && p.housenumber ? p.housenumber + ' ' + p.street : p.street]
                 .filter(Boolean).join(', ');
    const tail = [p.postcode, p.city || p.county || p.state, p.country].filter(Boolean).join(', ');
    return { head: head || tail, tail };
  }

  function render(){
    list.innerHTML = '';
    if (!hits.length){
      list.innerHTML = '<div class="res"><span class="lbl">Aucun résultat</span></div>';
      list.classList.add('show'); return;
    }
    hits.forEach(h => {
      const { head, tail } = labelOf(h.p);
      const row = document.createElement('div');
      row.className = 'res';
      const lbl = document.createElement('div');
      lbl.className = 'lbl';
      lbl.innerHTML = '<div>' + head + '</div><div class="sub">' + tail + '</div>';
      lbl.onclick = () => { map.setView([h.lat, h.lng], 13); list.classList.remove('show'); };
      row.appendChild(lbl);
      [['D','start'], ['A','end'], ['+','via']].forEach(([t, kind]) => {
        const b = document.createElement('button');
        b.className = 'mini'; b.textContent = t;
        b.title = kind === 'start' ? 'Départ' : kind === 'end' ? 'Arrivée' : 'Étape';
        b.onclick = ev => { ev.stopPropagation(); pick(h, kind); };
        row.appendChild(b);
      });
      list.appendChild(row);
    });
    list.classList.add('show');
  }

  function pick(h, kind){
    const ll = L.latLng(h.lat, h.lng);
    place(kind, ll);
    map.setView(ll, Math.max(map.getZoom(), 11));
    list.classList.remove('show');
    box.value = '';
    hint(kind === 'start' ? 'Départ défini' : kind === 'end' ? 'Arrivée définie' : 'Étape ajoutée');
  }

  /* ── persistance légère (ignorée si le navigateur bloque le storage de l'iframe) ── */
  function save(){
    try{
      sessionStorage.setItem('carte_manuelle_v2', JSON.stringify({
        start:S.start, end:S.end, vias:S.vias, tolls:S.tolls, hw:S.hw
      }));
    }catch(e){}
  }
  function restore(){
    try{
      const raw = sessionStorage.getItem('carte_manuelle_v2');
      if (!raw) return false;
      const d = JSON.parse(raw);
      if (!d || (!d.start && !d.end)) return false;
      S.start = d.start ? L.latLng(d.start.lat, d.start.lng) : null;
      S.end   = d.end   ? L.latLng(d.end.lat,   d.end.lng)   : null;
      S.vias  = (d.vias || []).map(v => L.latLng(v.lat, v.lng));
      S.tolls = !!d.tolls; S.hw = !!d.hw;
      $('tolls').checked = S.tolls; $('hw').checked = S.hw;
      redraw(); go();
      const pts = [S.start, ...S.vias, S.end].filter(Boolean);
      if (pts.length) map.fitBounds(L.latLngBounds(pts), { padding:[45,45] });
      return true;
    }catch(e){ return false; }
  }

  /* ── état serveur ── */
  async function ping(tries){
    try{
      const r = await fetch(SERVER + '/health', { cache:'no-store' });
      if (r.ok){ $('srv').className = 'dot up'; $('srv').title = 'Serveur carte en ligne'; return; }
      throw new Error();
    }catch(e){
      if (tries > 0){ setTimeout(() => ping(tries - 1), 5000); return; }
      $('srv').className = 'dot down';
      $('srv').title = 'Serveur carte injoignable';
      msg('Serveur carte injoignable — vérifiez ' + SERVER, 'err');
    }
  }

  ping(5);
  if (!restore()) msg('Cliquez sur la carte pour poser le départ, puis l\'arrivée.');
  setTimeout(() => map.invalidateSize(), 250);
  window.addEventListener('resize', () => map.invalidateSize());
})();
</script>
"""

components.html(MAP_HTML.replace("__SERVER_URL__", MAP_SERVER_URL), height=900, scrolling=False)

if not server_up:
    st.warning(
        f"Le serveur carte ({MAP_SERVER_URL}) n'a pas répondu au réveil. "
        "La carte reste utilisable : elle réessaie toute seule pendant ~25 s.",
        icon="⚠️",
    )
