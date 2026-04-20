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
/* ============================================================
   CB Groupe — Design Tokens
   Source of truth for colors, type, spacing, radii, shadows,
   gradients, and animations used across Transport Hub.
   ============================================================ */

/* ── Fonts ───────────────────────────────────────────────── */
/* Primary: Poppins (brand-supplied, shipped in fonts/).
   Mono:    JetBrains Mono (Google Fonts). */
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&display=swap');

@font-face { font-family: 'Poppins'; font-weight: 100; font-style: normal;  src: url('fonts/Poppins-Thin.ttf') format('truetype'); font-display: swap; }
@font-face { font-family: 'Poppins'; font-weight: 100; font-style: italic;  src: url('fonts/Poppins-ThinItalic.ttf') format('truetype'); font-display: swap; }
@font-face { font-family: 'Poppins'; font-weight: 200; font-style: normal;  src: url('fonts/Poppins-ExtraLight.ttf') format('truetype'); font-display: swap; }
@font-face { font-family: 'Poppins'; font-weight: 200; font-style: italic;  src: url('fonts/Poppins-ExtraLightItalic.ttf') format('truetype'); font-display: swap; }
@font-face { font-family: 'Poppins'; font-weight: 300; font-style: normal;  src: url('fonts/Poppins-Light.ttf') format('truetype'); font-display: swap; }
@font-face { font-family: 'Poppins'; font-weight: 300; font-style: italic;  src: url('fonts/Poppins-LightItalic.ttf') format('truetype'); font-display: swap; }
@font-face { font-family: 'Poppins'; font-weight: 400; font-style: normal;  src: url('fonts/Poppins-Regular.ttf') format('truetype'); font-display: swap; }
@font-face { font-family: 'Poppins'; font-weight: 400; font-style: italic;  src: url('fonts/Poppins-Italic.ttf') format('truetype'); font-display: swap; }
@font-face { font-family: 'Poppins'; font-weight: 500; font-style: normal;  src: url('fonts/Poppins-Medium.ttf') format('truetype'); font-display: swap; }
@font-face { font-family: 'Poppins'; font-weight: 500; font-style: italic;  src: url('fonts/Poppins-MediumItalic.ttf') format('truetype'); font-display: swap; }
@font-face { font-family: 'Poppins'; font-weight: 600; font-style: normal;  src: url('fonts/Poppins-SemiBold.ttf') format('truetype'); font-display: swap; }
@font-face { font-family: 'Poppins'; font-weight: 600; font-style: italic;  src: url('fonts/Poppins-SemiBoldItalic.ttf') format('truetype'); font-display: swap; }
@font-face { font-family: 'Poppins'; font-weight: 700; font-style: normal;  src: url('fonts/Poppins-Bold.ttf') format('truetype'); font-display: swap; }
@font-face { font-family: 'Poppins'; font-weight: 700; font-style: italic;  src: url('fonts/Poppins-BoldItalic.ttf') format('truetype'); font-display: swap; }
@font-face { font-family: 'Poppins'; font-weight: 800; font-style: normal;  src: url('fonts/Poppins-ExtraBold.ttf') format('truetype'); font-display: swap; }
@font-face { font-family: 'Poppins'; font-weight: 800; font-style: italic;  src: url('fonts/Poppins-ExtraBoldItalic.ttf') format('truetype'); font-display: swap; }
@font-face { font-family: 'Poppins'; font-weight: 900; font-style: normal;  src: url('fonts/Poppins-Black.ttf') format('truetype'); font-display: swap; }
@font-face { font-family: 'Poppins'; font-weight: 900; font-style: italic;  src: url('fonts/Poppins-BlackItalic.ttf') format('truetype'); font-display: swap; }

:root {
    /* ── Brand ─────────────────────────────────────────── */
    --cb-navy:         #1B3A5C;
    --cb-navy-light:   #244B73;
    --cb-navy-dark:    #122840;
    --cb-accent:       #4A90D9;
    --cb-accent-light: #6BA3E0;

    /* ── Surfaces (app background stops) ───────────────── */
    --cb-bg-0: #0F1923;  /* darkest — top-left of page gradient */
    --cb-bg-1: #152A3E;  /* mid    — 40% */
    --cb-bg-2: #1B3A5C;  /* bottom — 100%, == navy */
    --cb-sidebar-0: #0E1B28;
    --cb-sidebar-1: #152A3E;

    /* ── Neutrals ──────────────────────────────────────── */
    --cb-white:    #FFFFFF;
    --cb-gray-50:  #F8F9FC;
    --cb-gray-100: #EEF1F6;
    --cb-gray-200: #D8DDE6;  /* fg on dark bg — secondary body */
    --cb-gray-300: #C0CDE0;  /* fg on dark bg — primary body */
    --cb-gray-400: #8E99A9;  /* meta / muted */
    --cb-gray-600: #5A6577;  /* disabled / borders */

    /* ── Semantic ──────────────────────────────────────── */
    --cb-success: #2ECC71;
    --cb-warning: #F39C12;
    --cb-danger:  #E74C3C;
    --cb-info:    #4A90D9;   /* alias of accent */
    --cb-purple:  #8E44AD;   /* map search pin only */

    /* Map-specific (exception — light theme) */
    --cb-map-origin: #27ae60;
    --cb-map-dest:   #c0392b;
    --cb-map-wp:     #3498db;
    --cb-map-route:  #007cbf;
    --cb-map-ghost:  #95a5a6;

    /* ── Typography ────────────────────────────────────── */
    --font-sans: 'Poppins', 'Segoe UI', 'Arial', sans-serif;
    --font-mono: 'JetBrains Mono', 'SF Mono', Consolas, monospace;

    /* Size scale */
    --fs-hero:     2.6rem;  /* hero h1 */
    --fs-h1:       2.2rem;
    --fs-h2:       1.5rem;
    --fs-h3:       1.25rem; /* section title */
    --fs-card-title: 1.15rem;
    --fs-kpi:      2rem;
    --fs-kpi-lg:   2.5rem;
    --fs-body:     1rem;
    --fs-sm:       0.88rem;
    --fs-meta:     0.8rem;
    --fs-tiny:     0.78rem;
    --fs-micro:    0.65rem;

    --lh-tight: 1.2;
    --lh-body:  1.5;

    --fw-regular:  400;
    --fw-medium:   500;
    --fw-semibold: 600;
    --fw-bold:     700;
    --fw-black:    800;

    --tracking-tight: -0.5px;
    --tracking-wide:  1px;
    --tracking-xwide: 3px;

    /* ── Spacing scale (4-base) ────────────────────────── */
    --sp-0: 0;
    --sp-1: 4px;
    --sp-2: 8px;
    --sp-3: 12px;
    --sp-4: 16px;
    --sp-5: 24px;
    --sp-6: 32px;
    --sp-7: 40px;
    --sp-8: 56px;

    /* ── Radii ─────────────────────────────────────────── */
    --r-sm:  6px;
    --r-md:  10px;  /* buttons */
    --r-lg:  12px;
    --r-xl:  14px;  /* kpi cards */
    --r-2xl: 16px;  /* feature cards */
    --r-pill: 20px;
    --r-full: 999px;

    /* ── Borders ───────────────────────────────────────── */
    --border-rest:  1px solid rgba(74, 144, 217, 0.15);
    --border-hover: 1px solid rgba(74, 144, 217, 0.40);
    --border-kpi:   1px solid rgba(74, 144, 217, 0.10);
    --border-focus: 1px solid #4A90D9;

    /* ── Shadows / glows ───────────────────────────────── */
    --glow-soft:    0 0 20px rgba(74, 144, 217, 0.08);
    --glow-medium:  0 0 30px rgba(74, 144, 217, 0.18);
    --glow-hover:   0 12px 40px rgba(74, 144, 217, 0.15);
    --glow-button:  0 4px 20px rgba(74, 144, 217, 0.25);
    --glow-input:   0 0 10px rgba(74, 144, 217, 0.20);

    /* ── Gradients ─────────────────────────────────────── */
    --grad-page:    linear-gradient(160deg, #0F1923 0%, #152A3E 40%, #1B3A5C 100%);
    --grad-sidebar: linear-gradient(180deg, #0E1B28 0%, #152A3E 100%);
    --grad-card:    linear-gradient(145deg, rgba(21, 42, 62, 0.7), rgba(14, 27, 40, 0.9));
    --grad-kpi:     linear-gradient(145deg, rgba(21, 42, 62, 0.5), rgba(14, 27, 40, 0.7));
    --grad-button:  linear-gradient(135deg, #1B3A5C 0%, #244B73 100%);
    --grad-divider: linear-gradient(90deg, transparent, rgba(74, 144, 217, 0.30), transparent);
    --grad-card-topline: linear-gradient(90deg, transparent, #4A90D9, transparent);
    --grad-shimmer: linear-gradient(90deg, #4A90D9, #6BA3E0, #4A90D9, #6BA3E0);
    --grad-bar-ok:   linear-gradient(90deg, #2ECC71, #4A90D9);
    --grad-bar-warn: linear-gradient(90deg, #F39C12, #e67e22);
    --grad-bar-dng:  linear-gradient(90deg, #E74C3C, #c0392b);

    /* ── Motion ────────────────────────────────────────── */
    --ease-std:   cubic-bezier(0.25, 0.46, 0.45, 0.94);
    --ease-out:   ease-out;
    --dur-fast:   0.2s;
    --dur-base:   0.3s;
    --dur-card:   0.35s;
    --dur-slow:   0.7s;
}

/* ============================================================
   Semantic element tokens — apply these directly to elements
   ============================================================ */

html, body {
    font-family: var(--font-sans);
    font-size: 16px;
    line-height: var(--lh-body);
    color: var(--cb-gray-300);
    background: var(--grad-page);
    background-attachment: fixed;
}

h1, .cb-h1 {
    font-size: var(--fs-hero);
    font-weight: var(--fw-bold);
    line-height: var(--lh-tight);
    letter-spacing: var(--tracking-tight);
    color: var(--cb-white);
    margin: 0;
}

h2, .cb-h2 {
    font-size: var(--fs-h1);
    font-weight: var(--fw-bold);
    line-height: var(--lh-tight);
    color: var(--cb-white);
    margin: 0;
}

h3, .cb-h3, .cb-section-title {
    font-size: var(--fs-h3);
    font-weight: var(--fw-semibold);
    color: var(--cb-white);
    margin: 0;
}

.cb-card-title {
    font-size: var(--fs-card-title);
    font-weight: var(--fw-semibold);
    color: var(--cb-white);
}

.cb-kpi-value {
    font-size: var(--fs-kpi);
    font-weight: var(--fw-bold);
    color: var(--cb-white);
    line-height: var(--lh-tight);
}

.cb-kpi-value.accent { color: var(--cb-accent); }
.cb-kpi-value.success { color: var(--cb-success); }
.cb-kpi-value.danger { color: var(--cb-danger); }

p, .cb-p {
    font-size: var(--fs-body);
    line-height: var(--lh-body);
    color: var(--cb-gray-300);
    margin: 0 0 var(--sp-3) 0;
}

.cb-sm, .cb-help {
    font-size: var(--fs-sm);
    color: var(--cb-gray-400);
}

.cb-meta {
    font-size: var(--fs-meta);
    color: var(--cb-gray-400);
}

.cb-tracked-label {
    font-size: var(--fs-tiny);
    font-weight: var(--fw-medium);
    text-transform: uppercase;
    letter-spacing: var(--tracking-wide);
    color: var(--cb-gray-400);
}

.cb-sidebar-label {
    font-size: var(--fs-sm);
    font-weight: var(--fw-semibold);
    letter-spacing: var(--tracking-wide);
    color: var(--cb-accent);
}

code, .cb-code {
    font-family: var(--font-mono);
    font-size: 0.92em;
}

/* Shimmer treatment for single branded word in hero */
.cb-shimmer {
    background: var(--grad-shimmer);
    background-size: 200% auto;
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
    color: transparent;
    animation: cb-shimmer 4s linear infinite;
}

@keyframes cb-shimmer {
    0%   { background-position: -200% center; }
    100% { background-position:  200% center; }
}

@keyframes cb-fade-in-up {
    from { opacity: 0; transform: translateY(24px); }
    to   { opacity: 1; transform: translateY(0); }
}

@keyframes cb-fade-in-left {
    from { opacity: 0; transform: translateX(-20px); }
    to   { opacity: 1; transform: translateX(0); }
}

@keyframes cb-pulse-glow {
    0%, 100% { box-shadow: 0 0 20px rgba(74, 144, 217, 0.08); }
    50%      { box-shadow: 0 0 30px rgba(74, 144, 217, 0.18); }
}
</style>
""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="text-align:center; padding: 1rem 0;">
        <div style="background: var(--cb-navy); display: inline-block; padding: 12px 20px; border-radius: 12px; border: 1px solid rgba(74,144,217,0.3);">
            <div style="color: white; font-size: 1.8rem; font-weight: 800; line-height: 1;">CB</div>
            <div style="color: var(--cb-gray-400); font-size: 0.65rem; letter-spacing: 3px; text-transform: uppercase;">GROUPE</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(f'<p style="text-align:center; color:#8E99A9; font-size:0.8rem;">{APP_NAME} · v{VERSION}</p>', unsafe_allow_html=True)
    st.divider()

    # Paramètres interactifs
    st.markdown('<p style="color:#4A90D9; font-weight:600; font-size:0.85rem; letter-spacing:1px;">⚙️ PARAMÈTRES</p>', unsafe_allow_html=True)
    nb_camions     = st.number_input("Camions actifs",       min_value=0,   value=0, step=1)
    cout_carburant = st.number_input("Coût carburant (€)",   min_value=0.0, value=0.0, step=50.0, format="%.2f")
    km_parcourus   = st.number_input("Km parcourus",         min_value=0,   value=0, step=100)
    nb_alertes     = st.number_input("Alertes en cours",     min_value=0,   value=0, step=1)

    st.divider()

    # Notes rapides
    st.markdown('<p style="color:#4A90D9; font-weight:600; font-size:0.85rem; letter-spacing:1px;">📝 NOTES DU JOUR</p>', unsafe_allow_html=True)
    if "notes" not in st.session_state:
        st.session_state.notes = []

    nouvelle_note = st.text_input("Nouvelle note", label_visibility="collapsed", placeholder="Écrire une note...")
    if st.button("➕ Ajouter", use_container_width=True) and nouvelle_note:
        st.session_state.notes.append({
            "heure": datetime.now().strftime("%H:%M"),
            "note": nouvelle_note
        })
        st.rerun()

# ── Hero Section ──────────────────────────────────────────────
st.markdown(f"""
<div class="cb-hero">
    <div style="display: flex; align-items: center; justify-content: space-between;">
        <div>
            <h1>Tableau de bord <span>CB Groupe</span></h1>
            <p>Bienvenue — {datetime.now().strftime("%A %d %B %Y, %H:%M")}</p>
        </div>
        <div class="cb-status online">
            <span class="cb-status-dot"></span>
            Système actif
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

st.markdown('<div class="cb-divider"></div>', unsafe_allow_html=True)

# ── KPIs ──────────────────────────────────────────────────────
st.markdown('<div class="cb-section-title"><span class="dot"></span> Indicateurs clés</div>', unsafe_allow_html=True)

k1, k2, k3, k4 = st.columns(4)

with k1:
    st.markdown(f"""
    <div class="cb-kpi-card cb-kpi-delay-1">
        <div class="kpi-label">🚛 Camions actifs</div>
        <div class="kpi-value accent">{nb_camions}</div>
    </div>""", unsafe_allow_html=True)

with k2:
    alert_color = "accent" if nb_alertes <= 3 else ""
    alert_style = f"color: var(--cb-danger);" if nb_alertes > 3 else ""
    st.markdown(f"""
    <div class="cb-kpi-card cb-kpi-delay-2">
        <div class="kpi-label">⚠️ Alertes</div>
        <div class="kpi-value" style="{alert_style}">{nb_alertes}</div>
    </div>""", unsafe_allow_html=True)

with k3:
    km_fmt = f"{km_parcourus:,}".replace(",", " ")
    st.markdown(f"""
    <div class="cb-kpi-card cb-kpi-delay-3">
        <div class="kpi-label">🛣️ Km parcourus</div>
        <div class="kpi-value">{km_fmt}</div>
    </div>""", unsafe_allow_html=True)

with k4:
    cout_fmt = f"{cout_carburant:,.2f}".replace(",", " ")
    st.markdown(f"""
    <div class="cb-kpi-card cb-kpi-delay-4">
        <div class="kpi-label">⛽ Carburant</div>
        <div class="kpi-value">{cout_fmt} €</div>
    </div>""", unsafe_allow_html=True)

# ── Ratio coût/km ─────────────────────────────────────────────
if km_parcourus > 0:
    ratio = cout_carburant / km_parcourus
    pct   = min(ratio / 0.8 * 100, 100)
    bar_class = "danger" if ratio >= 0.5 else ("warn" if ratio >= 0.3 else "")

    st.markdown('<div class="cb-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="cb-section-title"><span class="dot"></span> Ratio coût / km</div>', unsafe_allow_html=True)

    rc1, rc2 = st.columns([1, 3])
    with rc1:
        st.markdown(f"""
        <div class="cb-kpi-card">
            <div class="kpi-label">€ / km</div>
            <div class="kpi-value accent">{ratio:.3f}</div>
        </div>""", unsafe_allow_html=True)

    with rc2:
        label = "✅ Excellent" if ratio < 0.3 else ("⚠️ Attention" if ratio < 0.5 else "🔴 Trop élevé")
        st.markdown(f"""
        <div style="padding: 1rem 0;">
            <p style="color: var(--cb-gray-200); margin-bottom: 0.5rem; font-size: 1rem;">{label} — <strong>{ratio:.3f} €/km</strong></p>
            <div class="cb-ratio-bar">
                <div class="cb-ratio-fill {bar_class}" style="width: {pct}%;"></div>
            </div>
            <p style="color: var(--cb-gray-400); font-size: 0.78rem; margin-top: 0.4rem;">Seuil recommandé : &lt; 0.30 €/km</p>
        </div>""", unsafe_allow_html=True)

st.markdown('<div class="cb-divider"></div>', unsafe_allow_html=True)

# ── Modules ───────────────────────────────────────────────────
st.markdown('<div class="cb-section-title"><span class="dot"></span> Modules</div>', unsafe_allow_html=True)

c1, c2, c3, c4 = st.columns(4)

modules = [
    ("🚛", "TX-FLEX",        "Analyse de flotte et performance transport",   "pages/1_🚛_Analyse_TX_FLEX.py"),
    ("🗺️", "Calcul KM",      "Distances PTV et optimisation itinéraires",    "pages/2_🗺️_Calcul_KM.py"),
    ("📍", "Carte Manuelle",  "Visualisation interactive des trajets",        "pages/3_🗺️_Carte_Manuelle.py"),
    ("🔗", "Ressources",      "Fichiers, documents et liens partagés",        "pages/4_🔗_Ressources.py"),
]

for i, (col, (icon, title, desc, page)) in enumerate(zip([c1, c2, c3, c4], modules)):
    with col:
        st.markdown(f"""
        <div class="cb-card cb-card-delay-{i+1}">
            <span class="cb-card-icon">{icon}</span>
            <h3>{title}</h3>
            <p>{desc}</p>
        </div>""", unsafe_allow_html=True)
        if st.button(f"Ouvrir {title}", key=f"btn_{i}", use_container_width=True):
            st.switch_page(page)

# ── Notes ─────────────────────────────────────────────────────
if st.session_state.notes:
    st.markdown('<div class="cb-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="cb-section-title"><span class="dot"></span> Notes du jour</div>', unsafe_allow_html=True)

    for i, n in enumerate(st.session_state.notes):
        col_n, col_x = st.columns([12, 1])
        with col_n:
            st.markdown(f"""
            <div class="cb-note">
                <span class="note-time">{n['heure']}</span>
                <span class="note-text"> — {n['note']}</span>
            </div>""", unsafe_allow_html=True)
        with col_x:
            if st.button("✕", key=f"del_{i}"):
                st.session_state.notes.pop(i)
                st.rerun()
