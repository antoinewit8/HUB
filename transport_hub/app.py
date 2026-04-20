# app.py
import streamlit as st
from datetime import datetime
from core.config  import APP_NAME, VERSION
from core.session import init_session

# ── Configuration ─────────────────────────────────────────────
st.set_page_config(
    page_title = APP_NAME,
    page_icon  = "🚛",
    layout     = "wide",
    initial_sidebar_state = "expanded",
)
init_session()

# ── CSS Custom — Style CB Groupe ──────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
    --font-sans: 'Poppins', 'Segoe UI', Arial, sans-serif;
    --font-mono: 'JetBrains Mono', 'SF Mono', Consolas, monospace;
    --cb-navy:         #1B3A5C;
    --cb-navy-light:   #244B73;
    --cb-navy-dark:    #122840;
    --cb-accent:       #4A90D9;
    --cb-accent-light: #6BA3E0;
    --cb-white:        #FFFFFF;
    --cb-gray-200:     #D8DDE6;
    --cb-gray-300:     #C0CDE0;
    --cb-gray-400:     #8E99A9;
    --cb-gray-600:     #5A6577;
    --cb-success:      #2ECC71;
    --cb-warning:      #F39C12;
    --cb-danger:       #E74C3C;
    --grad-page:    linear-gradient(160deg, #0F1923 0%, #152A3E 40%, #1B3A5C 100%);
    --grad-card:    linear-gradient(145deg, rgba(21,42,62,0.7), rgba(14,27,40,0.9));
    --grad-kpi:     linear-gradient(145deg, rgba(21,42,62,0.5), rgba(14,27,40,0.7));
}

.stApp {
    background: linear-gradient(160deg, #0F1923 0%, #152A3E 40%, #1B3A5C 100%);
    font-family: var(--font-sans) !important;
}

section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0E1B28 0%, #152A3E 100%) !important;
    border-right: 1px solid rgba(74,144,217,0.15);
}
section[data-testid="stSidebar"] .stMarkdown p,
section[data-testid="stSidebar"] .stMarkdown li,
section[data-testid="stSidebar"] .stMarkdown h3 { color: var(--cb-gray-200) !important; }

@keyframes fadeInUp   { from { opacity:0; transform:translateY(24px); } to { opacity:1; transform:translateY(0); } }
@keyframes fadeInLeft { from { opacity:0; transform:translateX(-20px); } to { opacity:1; transform:translateX(0); } }
@keyframes shimmer    { 0% { background-position:-200% center; } 100% { background-position:200% center; } }
@keyframes pulse-glow { 0%,100% { box-shadow:0 0 20px rgba(74,144,217,0.08); } 50% { box-shadow:0 0 30px rgba(74,144,217,0.18); } }
@keyframes dot-pulse  { 0%,100% { opacity:1; } 50% { opacity:0.4; } }

/* ── Hero ── */
.cb-hero { animation:fadeInUp 0.7s ease-out; padding:2.5rem 0 1rem 0; }
.cb-hero h1 { font-size:2.6rem; font-weight:700; color:var(--cb-white); margin:0; letter-spacing:-0.5px; line-height:1.2; }
.cb-hero h1 span {
    background: linear-gradient(90deg, var(--cb-accent), var(--cb-accent-light), var(--cb-accent), var(--cb-accent-light));
    background-size:200% auto; -webkit-background-clip:text; -webkit-text-fill-color:transparent;
    animation:shimmer 4s linear infinite;
}
.cb-hero p { color:var(--cb-gray-400); font-size:1.05rem; margin-top:0.4rem; }

/* ── Divider ── */
.cb-divider { height:1px; background:linear-gradient(90deg, transparent, rgba(74,144,217,0.3), transparent); margin:1.8rem 0; border:none; }

/* ── Section title ── */
.cb-section-title { color:var(--cb-white); font-size:1.25rem; font-weight:600; margin-bottom:1rem; display:flex; align-items:center; gap:0.6rem; animation:fadeInLeft 0.5s ease-out; }
.cb-section-title .dot { width:8px; height:8px; background:var(--cb-accent); border-radius:50%; display:inline-block; animation:pulse-glow 2s ease-in-out infinite; }

/* ── KPI Cards ── */
.cb-kpi-card { background:var(--grad-kpi); border:1px solid rgba(74,144,217,0.1); border-radius:14px; padding:1.4rem 1.3rem; animation:pulse-glow 4s ease-in-out infinite, fadeInUp 0.7s ease-out backwards; text-align:center; }
.cb-kpi-card .kpi-label { color:var(--cb-gray-400); font-size:0.8rem; text-transform:uppercase; letter-spacing:1px; margin-bottom:0.5rem; }
.cb-kpi-card .kpi-value { color:var(--cb-white); font-size:2rem; font-weight:700; }
.cb-kpi-card .kpi-value.accent { color:var(--cb-accent); }
.cb-kpi-card .kpi-value.danger { color:var(--cb-danger); }
.cb-kpi-delay-1 { animation-delay:0.15s; } .cb-kpi-delay-2 { animation-delay:0.30s; }
.cb-kpi-delay-3 { animation-delay:0.45s; } .cb-kpi-delay-4 { animation-delay:0.60s; }

/* ── Module Cards ── */
.cb-card { background:var(--grad-card); border:1px solid rgba(74,144,217,0.15); border-radius:16px; padding:1.8rem 1.5rem; transition:all 0.35s cubic-bezier(0.25,0.46,0.45,0.94); cursor:pointer; position:relative; overflow:hidden; animation:fadeInUp 0.6s ease-out backwards; }
.cb-card::before { content:''; position:absolute; top:0; left:0; right:0; height:3px; background:linear-gradient(90deg, transparent, var(--cb-accent), transparent); opacity:0; transition:opacity 0.35s; }
.cb-card:hover { transform:translateY(-6px); border-color:rgba(74,144,217,0.4); box-shadow:0 12px 40px rgba(74,144,217,0.15); }
.cb-card:hover::before { opacity:1; }
.cb-card-icon { font-size:2.2rem; margin-bottom:0.7rem; display:block; }
.cb-card h3 { color:var(--cb-white); font-size:1.15rem; font-weight:600; margin:0 0 0.4rem 0; }
.cb-card p  { color:var(--cb-gray-400); font-size:0.88rem; margin:0; line-height:1.5; }
.cb-card-delay-1 { animation-delay:0.1s; } .cb-card-delay-2 { animation-delay:0.2s; }
.cb-card-delay-3 { animation-delay:0.3s; } .cb-card-delay-4 { animation-delay:0.4s; }

/* ── Badges / Status ── */
.cb-status { display:inline-flex; align-items:center; gap:6px; padding:4px 12px; border-radius:20px; font-size:0.78rem; font-weight:500; }
.cb-status.online  { background:rgba(46,204,113,0.12); color:var(--cb-success); border:1px solid rgba(46,204,113,0.25); }
.cb-status.warn    { background:rgba(243,156,18,0.12);  color:var(--cb-warning); border:1px solid rgba(243,156,18,0.25); }
.cb-status.offline { background:rgba(231,76,60,0.12);   color:var(--cb-danger);  border:1px solid rgba(231,76,60,0.25); }
.cb-status-dot { width:6px; height:6px; border-radius:50%; background:currentColor; animation:dot-pulse 1.5s ease-in-out infinite; }

/* ── Tabs ── */
.cb-tabs { display:flex; gap:4px; border-bottom:1px solid rgba(74,144,217,0.15); margin-bottom:1.2rem; }
.cb-tab  { padding:0.6rem 1rem; color:var(--cb-gray-400); font-size:0.9rem; border-bottom:2px solid transparent; font-family:var(--font-sans); background:none; border-top:none; border-left:none; border-right:none; transition:all 0.25s ease; }
.cb-tab.active { color:var(--cb-accent); border-bottom-color:var(--cb-accent); }

/* ── Chips ── */
.cb-chips { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:1rem; }
.cb-chip  { background:rgba(74,144,217,0.1); border:1px solid rgba(74,144,217,0.3); color:var(--cb-accent); border-radius:20px; padding:0.3rem 1rem; font-size:0.8rem; }

/* ── Progress bars ── */
.cb-bar-row { display:flex; align-items:center; gap:14px; margin-bottom:10px; }
.cb-bar-lbl { color:var(--cb-gray-300); font-size:0.88rem; min-width:130px; }
.cb-bar     { flex:1; background:rgba(14,27,40,0.6); border-radius:10px; height:12px; overflow:hidden; }
.cb-bar-fill { height:100%; border-radius:10px; transition:width 0.8s ease-out; }
.cb-bar-fill.ok   { background:linear-gradient(90deg,#2ECC71,#4A90D9); }
.cb-bar-fill.warn { background:linear-gradient(90deg,#F39C12,#e67e22); }
.cb-bar-fill.dng  { background:linear-gradient(90deg,#E74C3C,#c0392b); }
.cb-bar-val { color:white; font-family:var(--font-mono); font-size:0.85rem; min-width:80px; text-align:right; }

/* ── Ratio bar ── */
.cb-ratio-bar  { background:rgba(14,27,40,0.6); border-radius:10px; height:12px; overflow:hidden; margin-top:0.5rem; }
.cb-ratio-fill { height:100%; border-radius:10px; transition:width 0.8s ease-out; background:linear-gradient(90deg,var(--cb-success),var(--cb-accent)); }
.cb-ratio-fill.warn   { background:linear-gradient(90deg,var(--cb-warning),#e67e22); }
.cb-ratio-fill.danger { background:linear-gradient(90deg,var(--cb-danger),#c0392b); }

/* ── Notes / Info ── */
.cb-note { background:rgba(21,42,62,0.4); border-left:3px solid var(--cb-accent); border-radius:0 10px 10px 0; padding:0.8rem 1rem; margin-bottom:0.6rem; animation:fadeInLeft 0.4s ease-out; }
.cb-note .note-time { color:var(--cb-accent); font-size:0.78rem; font-weight:600; }
.cb-note .note-text { color:var(--cb-gray-200); font-size:0.9rem; }
.cb-info { background:rgba(74,144,217,0.08); border-left:3px solid var(--cb-accent); border-radius:0 12px 12px 0; padding:1rem 1.5rem; color:var(--cb-gray-300); font-size:0.92rem; margin-bottom:0.6rem; }

/* ── Elevation cards ── */
.cb-elevation-row { display:flex; gap:20px; flex-wrap:wrap; align-items:flex-start; }
.cb-elev-card { background:var(--grad-card); border:1px solid rgba(74,144,217,0.15); border-radius:14px; padding:1.2rem 1.5rem; flex:1; min-width:140px; color:var(--cb-gray-300); font-size:0.85rem; text-align:center; transition:all 0.3s ease; }
.cb-elev-card.glow  { animation:pulse-glow 3s ease-in-out infinite; }
.cb-elev-card.hover { box-shadow:0 12px 40px rgba(74,144,217,0.15); border-color:rgba(74,144,217,0.4); transform:translateY(-4px); }
.cb-elev-lbl { color:var(--cb-gray-600); font-size:0.72rem; font-family:var(--font-mono); margin-top:6px; text-align:center; }

/* ── Emoji grid ── */
.cb-emoji-cell { text-align:center; margin-bottom:0.5rem; }
.cb-emoji-icon { font-size:1.6rem; background:var(--grad-card); border:1px solid rgba(74,144,217,0.15); border-radius:12px; padding:12px 6px; display:block; margin-bottom:4px; }
.cb-emoji-cap  { color:var(--cb-gray-400); font-size:0.7rem; display:block; }

/* ── Hide Streamlit defaults ── */
.stDeployButton, #MainMenu, footer, header { display:none !important; }
[data-testid="stMetricValue"] { color:var(--cb-white) !important; }
[data-testid="stMetricLabel"] { color:var(--cb-gray-400) !important; }

section[data-testid="stSidebar"] input { background:rgba(14,27,40,0.6) !important; border-color:rgba(74,144,217,0.2) !important; color:white !important; }
section[data-testid="stSidebar"] input:focus { border-color:var(--cb-accent) !important; box-shadow:0 0 10px rgba(74,144,217,0.2) !important; }

.stButton > button { background:linear-gradient(135deg,var(--cb-navy) 0%,var(--cb-navy-light) 100%) !important; color:white !important; border:1px solid rgba(74,144,217,0.3) !important; border-radius:10px !important; padding:0.5rem 1.2rem !important; font-weight:500 !important; transition:all 0.3s ease !important; font-family:var(--font-sans) !important; }
.stButton > button:hover { border-color:var(--cb-accent) !important; box-shadow:0 4px 20px rgba(74,144,217,0.25) !important; transform:translateY(-2px) !important; }
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("""
    <div style="text-align:center; padding:1rem 0;">
        <div style="background:var(--cb-navy); display:inline-block; padding:12px 20px;
                    border-radius:12px; border:1px solid rgba(74,144,217,0.3);">
            <div style="color:white; font-size:1.8rem; font-weight:800; line-height:1;">CB</div>
            <div style="color:var(--cb-gray-400); font-size:0.65rem; letter-spacing:3px; text-transform:uppercase;">GROUPE</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown(f'<p style="text-align:center;color:#8E99A9;font-size:0.8rem;">{APP_NAME} · v{VERSION}</p>',
                unsafe_allow_html=True)
    st.divider()

    st.markdown('<p style="color:#4A90D9;font-weight:600;font-size:0.85rem;letter-spacing:1px;">⚙️ PARAMÈTRES</p>',
                unsafe_allow_html=True)
    nb_camions     = st.number_input("Camions actifs",     min_value=0,   value=0,   step=1)
    cout_carburant = st.number_input("Coût carburant (€)", min_value=0.0, value=0.0, step=50.0, format="%.2f")
    km_parcourus   = st.number_input("Km parcourus",       min_value=0,   value=0,   step=100)
    nb_alertes     = st.number_input("Alertes en cours",   min_value=0,   value=0,   step=1)
    st.divider()

    st.markdown('<p style="color:#4A90D9;font-weight:600;font-size:0.85rem;letter-spacing:1px;">📝 NOTES DU JOUR</p>',
                unsafe_allow_html=True)
    if "notes" not in st.session_state:
        st.session_state.notes = []
    nouvelle_note = st.text_input("Nouvelle note", label_visibility="collapsed", placeholder="Écrire une note...")
    if st.button("➕ Ajouter", use_container_width=True) and nouvelle_note:
        st.session_state.notes.append({"heure": datetime.now().strftime("%H:%M"), "note": nouvelle_note})
        st.rerun()

# ══════════════════════════════════════════════════════════════
# HERO
# ══════════════════════════════════════════════════════════════
badge_class = "offline" if nb_alertes > 5 else ("warn" if nb_alertes > 3 else "online")
badge_label = "Alertes critiques" if nb_alertes > 5 else ("Attention" if nb_alertes > 3 else "Système actif")

st.markdown(f"""
<div class="cb-hero">
    <div style="display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:1rem;">
        <div>
            <h1>Tableau de bord <span>CB Groupe</span></h1>
            <p>Bienvenue — {datetime.now().strftime("%A %d %B %Y, %H:%M")}</p>
        </div>
        <div class="cb-status {badge_class}">
            <span class="cb-status-dot"></span>{badge_label}
        </div>
    </div>
</div>
""", unsafe_allow_html=True)
st.markdown('<div class="cb-divider"></div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
# KPIs
# ══════════════════════════════════════════════════════════════
st.markdown('<div class="cb-section-title"><span class="dot"></span> Indicateurs clés</div>', unsafe_allow_html=True)
k1, k2, k3, k4 = st.columns(4)
with k1:
    st.markdown(f'<div class="cb-kpi-card cb-kpi-delay-1"><div class="kpi-label">🚛 Camions actifs</div><div class="kpi-value accent">{nb_camions}</div></div>', unsafe_allow_html=True)
with k2:
    danger = 'style="color:var(--cb-danger);"' if nb_alertes > 3 else ""
    st.markdown(f'<div class="cb-kpi-card cb-kpi-delay-2"><div class="kpi-label">⚠️ Alertes</div><div class="kpi-value" {danger}>{nb_alertes}</div></div>', unsafe_allow_html=True)
with k3:
    km_fmt = f"{km_parcourus:,}".replace(",", " ")
    st.markdown(f'<div class="cb-kpi-card cb-kpi-delay-3"><div class="kpi-label">🛣️ Km parcourus</div><div class="kpi-value">{km_fmt}</div></div>', unsafe_allow_html=True)
with k4:
    cout_fmt = f"{cout_carburant:,.2f}".replace(",", " ")
    st.markdown(f'<div class="cb-kpi-card cb-kpi-delay-4"><div class="kpi-label">⛽ Carburant</div><div class="kpi-value">{cout_fmt} €</div></div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
# PERFORMANCES — progress bars + ratio
# ══════════════════════════════════════════════════════════════
st.markdown('<div class="cb-divider"></div>', unsafe_allow_html=True)
st.markdown('<div class="cb-section-title"><span class="dot"></span> Performances</div>', unsafe_allow_html=True)

if km_parcourus > 0:
    ratio     = cout_carburant / km_parcourus
    pct       = min(ratio / 0.8 * 100, 100)
    bar_class = "dng" if ratio >= 0.5 else ("warn" if ratio >= 0.3 else "ok")
    label_rat = "✅ Excellent" if ratio < 0.3 else ("⚠️ Attention" if ratio < 0.5 else "🔴 Trop élevé")
    rc1, rc2  = st.columns([1, 3])
    with rc1:
        st.markdown(f'<div class="cb-kpi-card"><div class="kpi-label">€ / km</div><div class="kpi-value accent">{ratio:.3f}</div></div>', unsafe_allow_html=True)
    with rc2:
        st.markdown(f"""
        <div style="padding:1rem 0;">
            <div class="cb-bar-row">
                <span class="cb-bar-lbl">{label_rat}</span>
                <div class="cb-bar"><div class="cb-bar-fill {bar_class}" style="width:{pct:.0f}%"></div></div>
                <span class="cb-bar-val">{ratio:.3f} €/km</span>
            </div>
            <p style="color:var(--cb-gray-400);font-size:0.78rem;margin-top:0.4rem;">Seuil recommandé : &lt; 0.30 €/km</p>
        </div>""", unsafe_allow_html=True)
else:
    st.markdown("""
    <div class="cb-bar-row"><span class="cb-bar-lbl">✅ Excellent</span><div class="cb-bar"><div class="cb-bar-fill ok" style="width:35%"></div></div><span class="cb-bar-val">0.180 €/km</span></div>
    <div class="cb-bar-row"><span class="cb-bar-lbl">⚠️ Attention</span><div class="cb-bar"><div class="cb-bar-fill warn" style="width:62%"></div></div><span class="cb-bar-val">0.375 €/km</span></div>
    <div class="cb-bar-row"><span class="cb-bar-lbl">🔴 Trop élevé</span><div class="cb-bar"><div class="cb-bar-fill dng" style="width:91%"></div></div><span class="cb-bar-val">0.540 €/km</span></div>
    <p style="color:var(--cb-gray-600);font-size:0.78rem;margin-top:0.4rem;">Entrez vos données dans la sidebar pour calculer votre ratio réel.</p>
    """, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
# STATUTS / BADGES
# ══════════════════════════════════════════════════════════════
st.markdown('<div class="cb-divider"></div>', unsafe_allow_html=True)
st.markdown('<div class="cb-section-title"><span class="dot"></span> Statuts système</div>', unsafe_allow_html=True)

api_class = "offline" if nb_alertes > 5 else "online"
api_label = "Serveur hors ligne" if nb_alertes > 5 else "API PTV connectée"
st.markdown(f"""
<div style="display:flex; gap:12px; flex-wrap:wrap; margin-bottom:1rem;">
    <span class="cb-status online"><span class="cb-status-dot"></span>Système actif</span>
    <span class="cb-status online">✅ Itinéraire original</span>
    <span class="cb-status warn">✏️ Itinéraire modifié</span>
    <span class="cb-status {api_class}"><span class="cb-status-dot"></span>{api_label}</span>
</div>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
# MODULES (tabs + cards)
# ══════════════════════════════════════════════════════════════
st.markdown('<div class="cb-divider"></div>', unsafe_allow_html=True)
st.markdown('<div class="cb-section-title"><span class="dot"></span> Modules</div>', unsafe_allow_html=True)
st.markdown("""
<div class="cb-tabs">
    <div class="cb-tab active">🗂️ Tous les modules</div>
    <div class="cb-tab">🚛 Flotte</div>
    <div class="cb-tab">🗺️ Cartographie</div>
</div>
""", unsafe_allow_html=True)

c1, c2, c3 = st.columns(3)
modules = [
    ("🚛", "TX-FLEX",        "Analyse de flotte et performance transport",  "pages/1___Analyse_TX_FLEX.py"),
    ("🗺️", "Calcul KM",      "Distances PTV et optimisation itinéraires",   "pages/2____Calcul_KM.py"),
    ("📍", "Carte Manuelle",  "Visualisation interactive des trajets",       "pages/3____Carte_Manuelle.py"),
]
for i, (col, (icon, title, desc, page)) in enumerate(zip([c1, c2, c3], modules)):
    with col:
        st.markdown(f"""
        <div class="cb-card cb-card-delay-{i+1}">
            <span class="cb-card-icon">{icon}</span>
            <h3>{title}</h3>
            <p>{desc}</p>
        </div>""", unsafe_allow_html=True)
        if st.button(f"Ouvrir {title}", key=f"btn_{i}", use_container_width=True):
            st.switch_page(page)

# ── Chips sources ──
st.markdown("""
<div class="cb-chips" style="margin-top:1rem;">
    <span class="cb-chip">📡 SPF Économie</span>
    <span class="cb-chip">📊 Excel / XLS</span>
    <span class="cb-chip">🗺️ PTV Routing</span>
    <span class="cb-chip">🔥 Firebase RTDB</span>
</div>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
# ELEVATION
# ══════════════════════════════════════════════════════════════
st.markdown('<div class="cb-divider"></div>', unsafe_allow_html=True)
st.markdown("<div class=\"cb-section-title\"><span class=\"dot\"></span> Niveaux d'élévation</div>", unsafe_allow_html=True)
st.markdown("""
<div class="cb-elevation-row">
    <div><div class="cb-elev-card">Repos</div><div class="cb-elev-lbl">no shadow</div></div>
    <div><div class="cb-elev-card glow">Pulse glow</div><div class="cb-elev-lbl">KPI · boucle 4s</div></div>
    <div><div class="cb-elev-card hover">Hover</div><div class="cb-elev-lbl">0 12px 40px / 15%</div></div>
</div>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
# ICONOGRAPHIE
# ══════════════════════════════════════════════════════════════
st.markdown('<div class="cb-divider"></div>', unsafe_allow_html=True)
st.markdown('<div class="cb-section-title"><span class="dot"></span> Iconographie</div>', unsafe_allow_html=True)
emojis = [
    ("🚛","fleet"), ("🗺️","map"), ("📍","pin"),  ("⛽","fuel"),
    ("🔗","link"),  ("📂","upload"), ("📥","download"), ("📊","chart"),
    ("⚙️","settings"), ("🔍","search"), ("🚀","launch"), ("🗑️","delete"),
]
cols = st.columns(6)
for i, (emoji, cap) in enumerate(emojis):
    with cols[i % 6]:
        st.markdown(f'<div class="cb-emoji-cell"><span class="cb-emoji-icon">{emoji}</span><span class="cb-emoji-cap">{cap}</span></div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
# INFO + NOTES
# ══════════════════════════════════════════════════════════════
st.markdown('<div class="cb-divider"></div>', unsafe_allow_html=True)
st.markdown('<div class="cb-section-title"><span class="dot"></span> Notes du jour</div>', unsafe_allow_html=True)
st.markdown('<div class="cb-info">🧮 <strong>Calculateur coût carburant</strong> — renseignez vos données dans la sidebar pour calculer le ratio €/km en temps réel.</div>', unsafe_allow_html=True)

if st.session_state.notes:
    for i, n in enumerate(st.session_state.notes):
        col_n, col_x = st.columns([12, 1])
        with col_n:
            st.markdown(f'<div class="cb-note"><span class="note-time">{n["heure"]}</span><span class="note-text"> — {n["note"]}</span></div>', unsafe_allow_html=True)
        with col_x:
            if st.button("✕", key=f"del_{i}"):
                st.session_state.notes.pop(i)
                st.rerun()
else:
    st.markdown('<div class="cb-note"><span class="note-time">--:--</span><span class="note-text"> — Aucune note. Ajoutez-en une depuis la sidebar.</span></div>', unsafe_allow_html=True)
