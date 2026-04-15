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
/* ── Variables couleurs CB ── */
:root {
    --cb-navy: #1B3A5C;
    --cb-navy-light: #244B73;
    --cb-navy-dark: #122840;
    --cb-accent: #4A90D9;
    --cb-accent-light: #6BA3E0;
    --cb-white: #FFFFFF;
    --cb-gray-50: #F8F9FC;
    --cb-gray-100: #EEF1F6;
    --cb-gray-200: #D8DDE6;
    --cb-gray-400: #8E99A9;
    --cb-gray-600: #5A6577;
    --cb-success: #2ECC71;
    --cb-warning: #F39C12;
    --cb-danger: #E74C3C;
}

/* ── Reset Streamlit background ── */
.stApp {
    background: linear-gradient(160deg, #0F1923 0%, #152A3E 40%, #1B3A5C 100%);
}

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0E1B28 0%, #152A3E 100%) !important;
    border-right: 1px solid rgba(74, 144, 217, 0.15);
}

section[data-testid="stSidebar"] .stMarkdown p,
section[data-testid="stSidebar"] .stMarkdown li,
section[data-testid="stSidebar"] .stMarkdown h3 {
    color: var(--cb-gray-200) !important;
}

/* ── Animations keyframes ── */
@keyframes fadeInUp {
    from { opacity: 0; transform: translateY(24px); }
    to   { opacity: 1; transform: translateY(0); }
}

@keyframes fadeInLeft {
    from { opacity: 0; transform: translateX(-20px); }
    to   { opacity: 1; transform: translateX(0); }
}

@keyframes shimmer {
    0%   { background-position: -200% center; }
    100% { background-position: 200% center; }
}

@keyframes pulse-glow {
    0%, 100% { box-shadow: 0 0 20px rgba(74, 144, 217, 0.08); }
    50%      { box-shadow: 0 0 30px rgba(74, 144, 217, 0.18); }
}

@keyframes borderGlow {
    0%, 100% { border-color: rgba(74, 144, 217, 0.2); }
    50%      { border-color: rgba(74, 144, 217, 0.45); }
}

/* ── Titre principal animé ── */
.cb-hero {
    animation: fadeInUp 0.7s ease-out;
    padding: 2.5rem 0 1rem 0;
}

.cb-hero h1 {
    font-size: 2.6rem;
    font-weight: 700;
    color: var(--cb-white);
    margin: 0;
    letter-spacing: -0.5px;
    line-height: 1.2;
}

.cb-hero h1 span {
    background: linear-gradient(90deg, var(--cb-accent), var(--cb-accent-light), var(--cb-accent), var(--cb-accent-light));
    background-size: 200% auto;
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    animation: shimmer 4s linear infinite;
}

.cb-hero p {
    color: var(--cb-gray-400);
    font-size: 1.05rem;
    margin-top: 0.4rem;
}

/* ── Divider custom ── */
.cb-divider {
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(74, 144, 217, 0.3), transparent);
    margin: 1.8rem 0;
    border: none;
}

/* ── Module cards ── */
.cb-card {
    background: linear-gradient(145deg, rgba(21, 42, 62, 0.7), rgba(14, 27, 40, 0.9));
    border: 1px solid rgba(74, 144, 217, 0.15);
    border-radius: 16px;
    padding: 1.8rem 1.5rem;
    transition: all 0.35s cubic-bezier(0.25, 0.46, 0.45, 0.94);
    cursor: pointer;
    position: relative;
    overflow: hidden;
    animation: fadeInUp 0.6s ease-out backwards;
}

.cb-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    background: linear-gradient(90deg, transparent, var(--cb-accent), transparent);
    opacity: 0;
    transition: opacity 0.35s;
}

.cb-card:hover {
    transform: translateY(-6px);
    border-color: rgba(74, 144, 217, 0.4);
    box-shadow: 0 12px 40px rgba(74, 144, 217, 0.15);
}

.cb-card:hover::before {
    opacity: 1;
}

.cb-card-icon {
    font-size: 2.2rem;
    margin-bottom: 0.7rem;
    display: block;
}

.cb-card h3 {
    color: var(--cb-white);
    font-size: 1.15rem;
    font-weight: 600;
    margin: 0 0 0.4rem 0;
}

.cb-card p {
    color: var(--cb-gray-400);
    font-size: 0.88rem;
    margin: 0;
    line-height: 1.5;
}

.cb-card-delay-1 { animation-delay: 0.1s; }
.cb-card-delay-2 { animation-delay: 0.2s; }
.cb-card-delay-3 { animation-delay: 0.3s; }
.cb-card-delay-4 { animation-delay: 0.4s; }

/* ── KPI Cards ── */
.cb-kpi-card {
    background: linear-gradient(145deg, rgba(21, 42, 62, 0.5), rgba(14, 27, 40, 0.7));
    border: 1px solid rgba(74, 144, 217, 0.1);
    border-radius: 14px;
    padding: 1.4rem 1.3rem;
    animation: pulse-glow 4s ease-in-out infinite, fadeInUp 0.7s ease-out backwards;
    text-align: center;
}

.cb-kpi-card .kpi-label {
    color: var(--cb-gray-400);
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 0.5rem;
}

.cb-kpi-card .kpi-value {
    color: var(--cb-white);
    font-size: 2rem;
    font-weight: 700;
}

.cb-kpi-card .kpi-value.accent {
    color: var(--cb-accent);
}

.cb-kpi-delay-1 { animation-delay: 0.15s; }
.cb-kpi-delay-2 { animation-delay: 0.3s; }
.cb-kpi-delay-3 { animation-delay: 0.45s; }
.cb-kpi-delay-4 { animation-delay: 0.6s; }

/* ── Section titles ── */
.cb-section-title {
    color: var(--cb-white);
    font-size: 1.25rem;
    font-weight: 600;
    margin-bottom: 1rem;
    display: flex;
    align-items: center;
    gap: 0.6rem;
    animation: fadeInLeft 0.5s ease-out;
}

.cb-section-title .dot {
    width: 8px; height: 8px;
    background: var(--cb-accent);
    border-radius: 50%;
    display: inline-block;
    animation: pulse-glow 2s ease-in-out infinite;
}

/* ── Status badge ── */
.cb-status {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 0.78rem;
    font-weight: 500;
}

.cb-status.online {
    background: rgba(46, 204, 113, 0.12);
    color: var(--cb-success);
    border: 1px solid rgba(46, 204, 113, 0.25);
}

.cb-status-dot {
    width: 6px; height: 6px;
    background: var(--cb-success);
    border-radius: 50%;
    animation: pulse-glow 1.5s ease-in-out infinite;
}

/* ── Notes container ── */
.cb-note {
    background: rgba(21, 42, 62, 0.4);
    border-left: 3px solid var(--cb-accent);
    border-radius: 0 10px 10px 0;
    padding: 0.8rem 1rem;
    margin-bottom: 0.6rem;
    animation: fadeInLeft 0.4s ease-out;
}

.cb-note .note-time {
    color: var(--cb-accent);
    font-size: 0.78rem;
    font-weight: 600;
}

.cb-note .note-text {
    color: var(--cb-gray-200);
    font-size: 0.9rem;
}

/* ── Ratio bar ── */
.cb-ratio-bar {
    background: rgba(14, 27, 40, 0.6);
    border-radius: 10px;
    height: 12px;
    overflow: hidden;
    margin-top: 0.5rem;
}

.cb-ratio-fill {
    height: 100%;
    border-radius: 10px;
    transition: width 0.8s ease-out;
    background: linear-gradient(90deg, var(--cb-success), var(--cb-accent));
}

.cb-ratio-fill.warn {
    background: linear-gradient(90deg, var(--cb-warning), #e67e22);
}

.cb-ratio-fill.danger {
    background: linear-gradient(90deg, var(--cb-danger), #c0392b);
}

/* ── Hide Streamlit default elements ── */
.stDeployButton, #MainMenu, footer, header { display: none !important; }

/* ── Streamlit metric override ── */
[data-testid="stMetricValue"] {
    color: var(--cb-white) !important;
}
[data-testid="stMetricLabel"] {
    color: var(--cb-gray-400) !important;
}

/* ── Input styling ── */
section[data-testid="stSidebar"] input {
    background: rgba(14, 27, 40, 0.6) !important;
    border-color: rgba(74, 144, 217, 0.2) !important;
    color: white !important;
}

section[data-testid="stSidebar"] input:focus {
    border-color: var(--cb-accent) !important;
    box-shadow: 0 0 10px rgba(74, 144, 217, 0.2) !important;
}

/* ── Buttons ── */
.stButton > button {
    background: linear-gradient(135deg, var(--cb-navy) 0%, var(--cb-navy-light) 100%) !important;
    color: white !important;
    border: 1px solid rgba(74, 144, 217, 0.3) !important;
    border-radius: 10px !important;
    padding: 0.5rem 1.2rem !important;
    font-weight: 500 !important;
    transition: all 0.3s ease !important;
}

.stButton > button:hover {
    border-color: var(--cb-accent) !important;
    box-shadow: 0 4px 20px rgba(74, 144, 217, 0.25) !important;
    transform: translateY(-2px) !important;
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

c1, c2, c3 = st.columns(3)

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
