# pages/5_⛽_Prix_Gasoil.py
"""
Module Prix Gasoil Belgique — Données officielles SPF Economie
"""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta

st.set_page_config(page_title="Prix Gasoil — CB Groupe", page_icon="⛽", layout="wide")

# ── CSS CB Groupe ─────────────────────────────────────────────
st.markdown("""
<style>
:root {
    --cb-navy: #1B3A5C;
    --cb-accent: #4A90D9;
    --cb-white: #FFFFFF;
}
.stApp {
    background: linear-gradient(160deg, #0F1923 0%, #152A3E 40%, #1B3A5C 100%);
}
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0E1B28 0%, #152A3E 100%) !important;
    border-right: 1px solid rgba(74, 144, 217, 0.15);
}

@keyframes fadeInUp {
    from { opacity: 0; transform: translateY(20px); }
    to   { opacity: 1; transform: translateY(0); }
}

.fuel-header {
    text-align: center;
    padding: 2rem 0;
    animation: fadeInUp 0.6s ease;
}
.fuel-header h1 {
    color: var(--cb-white);
    font-size: 2.2rem;
    margin: 0;
}
.fuel-header .sub {
    color: #8E99A9;
    font-size: 1rem;
    margin-top: 0.3rem;
}

.price-card {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(74,144,217,0.2);
    border-radius: 16px;
    padding: 1.5rem;
    text-align: center;
    animation: fadeInUp 0.7s ease;
    transition: all 0.3s ease;
}
.price-card:hover {
    border-color: rgba(74,144,217,0.5);
    transform: translateY(-4px);
    box-shadow: 0 8px 24px rgba(74,144,217,0.15);
}
.price-card .label {
    color: #8E99A9;
    font-size: 0.85rem;
    text-transform: uppercase;
    letter-spacing: 1px;
}
.price-card .price {
    color: var(--cb-white);
    font-size: 2.5rem;
    font-weight: 700;
    margin: 0.5rem 0;
}
.price-card .unit {
    color: var(--cb-accent);
    font-size: 0.9rem;
}
.price-card .trend-up   { color: #E74C3C; }
.price-card .trend-down { color: #2ECC71; }
.price-card .trend-flat { color: #8E99A9; }

.info-box {
    background: rgba(74,144,217,0.08);
    border-left: 3px solid var(--cb-accent);
    border-radius: 0 12px 12px 0;
    padding: 1rem 1.5rem;
    color: #C0CDE0;
    margin: 1rem 0;
    animation: fadeInUp 0.8s ease;
}

.stat-row {
    display: flex;
    justify-content: space-between;
    padding: 0.5rem 0;
    border-bottom: 1px solid rgba(255,255,255,0.05);
    color: #C0CDE0;
    font-size: 0.95rem;
}
.stat-row .stat-label { color: #8E99A9; }
.stat-row .stat-value { color: var(--cb-white); font-weight: 600; }

.source-badge {
    display: inline-block;
    background: rgba(74,144,217,0.1);
    border: 1px solid rgba(74,144,217,0.3);
    border-radius: 20px;
    padding: 0.3rem 1rem;
    color: var(--cb-accent);
    font-size: 0.8rem;
    margin-top: 1rem;
}
</style>
""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────
st.markdown("""
<div class="fuel-header">
    <h1>⛽ Prix du Gasoil — Belgique</h1>
    <div class="sub">Données officielles SPF Economie • Mise à jour automatique</div>
</div>
""", unsafe_allow_html=True)

# ── Chargement des données ────────────────────────────────────
from tools.fuel_scraper import get_all_prices, get_tarif_en_vigueur
from tools.fuel_avg_scraper import get_monthly_averages

with st.spinner("🔄 Récupération des prix officiels..."):
    # Tarif en vigueur
    tarif = get_tarif_en_vigueur()

    # Historique
    df = get_all_prices()

# ── Affichage tarif en vigueur ────────────────────────────────
if "prices" in tarif and tarif["prices"]:
    st.markdown("""
    <div class="info-box">
        📋 <strong>Tarif en vigueur</strong> — {label}
    </div>
    """.format(label=tarif.get("label", "N/A")), unsafe_allow_html=True)

    cols = st.columns(len(tarif["prices"]))
    for col, (fuel_type, price) in zip(cols, tarif["prices"].items()):
        nice_name = fuel_type.replace("_", " ").title()
        with col:
            st.markdown(f"""
            <div class="price-card">
                <div class="label">{nice_name}</div>
                <div class="price">{price:.4f}</div>
                <div class="unit">€ / litre (TTC)</div>
            </div>
            """, unsafe_allow_html=True)
else:
    st.warning("⚠️ Impossible de lire le tarif en vigueur. Vérifiez la connexion.")

# ── Historique & Graphiques ───────────────────────────────────
st.markdown("<br>", unsafe_allow_html=True)

if not df.empty:
    tab_daily, tab_monthly = st.tabs(["🕒 Suivi Quotidien", "📊 Moyennes Mensuelles (be.STAT)"])

    with tab_daily:
        # ── Filtre type de carburant ──
        fuel_types = df["type"].unique().tolist()
        selected_fuel = st.selectbox(
            "Type de carburant",
            fuel_types,
            index=fuel_types.index("diesel_routier") if "diesel_routier" in fuel_types else 0
        )

        df_fuel = df[df["type"] == selected_fuel].copy()

        if not df_fuel.empty:
            # ── KPIs ──
            st.markdown("<br>", unsafe_allow_html=True)
            k1, k2, k3, k4 = st.columns(4)

            prix_actuel = df_fuel.iloc[-1]["prix"]
            prix_moyen  = df_fuel["prix"].mean()
            prix_min    = df_fuel["prix"].min()
            prix_max    = df_fuel["prix"].max()

            # Tendance
            if len(df_fuel) >= 2:
                diff = df_fuel.iloc[-1]["prix"] - df_fuel.iloc[-2]["prix"]
                if diff > 0.005:
                    trend_icon, trend_class = "📈", "trend-up"
                    trend_text = f"+{diff:.4f}"
                elif diff < -0.005:
                    trend_icon, trend_class = "📉", "trend-down"
                    trend_text = f"{diff:.4f}"
                else:
                    trend_icon, trend_class = "➡️", "trend-flat"
                    trend_text = "stable"
            else:
                trend_icon, trend_class, trend_text = "➡️", "trend-flat", "N/A"

            with k1:
                st.markdown(f"""
                <div class="price-card">
                    <div class="label">Dernier prix</div>
                    <div class="price">{prix_actuel:.4f}€</div>
                    <div class="{trend_class}">{trend_icon} {trend_text}</div>
                </div>""", unsafe_allow_html=True)

            with k2:
                st.markdown(f"""
                <div class="price-card">
                    <div class="label">Moyenne</div>
                    <div class="price">{prix_moyen:.4f}€</div>
                    <div class="unit">sur {len(df_fuel)} mois</div>
                </div>""", unsafe_allow_html=True)

            with k3:
                st.markdown(f"""
                <div class="price-card">
                    <div class="label">Minimum</div>
                    <div class="price" style="color:#2ECC71">{prix_min:.4f}€</div>
                    <div class="unit">/litre</div>
                </div>""", unsafe_allow_html=True)

            with k4:
                st.markdown(f"""
                <div class="price-card">
                    <div class="label">Maximum</div>
                    <div class="price" style="color:#E74C3C">{prix_max:.4f}€</div>
                    <div class="unit">/litre</div>
                </div>""", unsafe_allow_html=True)

            # ── Graphique évolution ──
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown("""
            <div class="info-box">
                📊 <strong>Évolution du prix</strong> — {fuel}
            </div>
            """.format(fuel=selected_fuel.replace("_", " ").title()), unsafe_allow_html=True)

            fig = go.Figure()

            fig.add_trace(go.Scatter(
                x=df_fuel["date"],
                y=df_fuel["prix"],
                mode="lines+markers",
                name=selected_fuel.replace("_", " ").title(),
                line=dict(color="#4A90D9", width=3),
                marker=dict(size=8, color="#4A90D9", line=dict(width=2, color="#FFFFFF")),
                fill="tozeroy",
                fillcolor="rgba(74, 144, 217, 0.1)",
                hovertemplate="<b>%{x|%B %Y}</b><br>Prix: %{y:.4f} €/L<extra></extra>",
            ))

            # Ligne moyenne
            fig.add_hline(
                y=prix_moyen,
                line_dash="dash",
                line_color="rgba(255,255,255,0.3)",
                annotation_text=f"Moyenne: {prix_moyen:.4f}€",
                annotation_font_color="rgba(255,255,255,0.6)",
            )

            fig.update_layout(
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#C0CDE0"),
                xaxis=dict(
                    gridcolor="rgba(255,255,255,0.05)",
                    title="",
                ),
                yaxis=dict(
                    gridcolor="rgba(255,255,255,0.05)",
                    title="€ / litre (TTC)",
                    tickformat=".4f",
                ),
                margin=dict(l=60, r=20, t=20, b=40),
                height=400,
                hovermode="x unified",
            )

            st.plotly_chart(fig, use_container_width=True)

            # ── Tableau détaillé ──
            with st.expander("📋 Données détaillées"):
                df_display = df_fuel[["date", "prix", "source"]].copy()
                df_display["date"] = df_display["date"].dt.strftime("%B %Y")
                df_display.columns = ["Période", "Prix €/L", "Source PDF"]
                st.dataframe(df_display, use_container_width=True, hide_index=True)

    # ── Comparaison tous types ──
    if len(fuel_types) > 1:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("""
        <div class="info-box">
            🔄 <strong>Comparaison tous types de gasoil</strong>
        </div>
        """, unsafe_allow_html=True)

        fig2 = px.line(
            df,
            x="date",
            y="prix",
            color="type",
            markers=True,
            labels={"prix": "€/L (TTC)", "date": "", "type": "Type"},
            color_discrete_sequence=["#4A90D9", "#2ECC71", "#F39C12", "#E74C3C"],
        )
        fig2.update_layout(
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#C0CDE0"),
            xaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
            yaxis=dict(gridcolor="rgba(255,255,255,0.05)", tickformat=".4f"),
            legend=dict(bgcolor="rgba(0,0,0,0)"),
            margin=dict(l=60, r=20, t=20, b=40),
            height=350,
        )
        st.plotly_chart(fig2, use_container_width=True)

    # ── Analyse sur période personnalisée ──
    st.markdown("<br>", unsafe_allow_html=True)
    with st.expander("📊 Moyenne des prix (Analyse par période)"):
        today = datetime.now().date()
        start_default = today - timedelta(days=30)
        
        date_range = st.date_input(
            "Choisir une plage de dates",
            value=(start_default, today),
            max_value=today,
            help="Filtrer l'historique pour calculer les moyennes sur une période donnée"
        )

        if isinstance(date_range, tuple) and len(date_range) == 2:
            d_start, d_end = date_range
            # Filtrage sur la période sélectionnée pour le carburant choisi
            df_period = df_fuel[(df_fuel["date"].dt.date >= d_start) & (df_fuel["date"].dt.date <= d_end)].copy()
            
            if not df_period.empty:
                pmoy = df_period["prix"].mean()
                pmin = df_period["prix"].min()
                pmax = df_period["prix"].max()
                n_obs = len(df_period)
                
                st.markdown(f"**Analyse pour :** {selected_fuel.replace('_', ' ').title()}")
                c_k1, c_k2, c_k3, c_k4 = st.columns(4)
                c_k1.metric("Prix moyen", f"{pmoy:.4f} €/L")
                c_k2.metric("Minimum", f"{pmin:.4f} €/L")
                c_k3.metric("Maximum", f"{pmax:.4f} €/L")
                c_k4.metric("Relevés", n_obs)
                
                st.area_chart(df_period.set_index("date")["prix"], color="#4A90D9")
            else:
                st.warning(f"⚠️ Aucune donnée n'existe pour la période du {d_start} au {d_end} ({selected_fuel.replace('_', ' ').title()}).")

    with tab_monthly:
        with st.spinner("📊 Calcul des moyennes mensuelles..."):
            df_avg = get_monthly_averages()
            
        if not df_avg.empty:
            # KPIs pour le Gasoil Routier (le plus pertinent pour CB Groupe)
            avg_glob = df_avg["gasoil_routier"].mean()
            max_row = df_avg.loc[df_avg["gasoil_routier"].idxmax()]
            min_row = df_avg.loc[df_avg["gasoil_routier"].idxmin()]
            
            st.markdown("### 📈 Analyse Long Terme (Routier)")
            mk1, mk2, mk3 = st.columns(3)
            mk1.metric("Moyenne Globale", f"{avg_glob:.4f} €/L")
            mk2.metric("Mois le plus cher", f"{max_row['gasoil_routier']:.4f} €/L", max_row["date"].strftime("%b %Y"), delta_color="inverse")
            mk3.metric("Mois le moins cher", f"{min_row['gasoil_routier']:.4f} €/L", min_row["date"].strftime("%b %Y"))
            
            st.markdown("<br>", unsafe_allow_html=True)
            
            # Graphique d'évolution
            st.markdown("**Évolution des moyennes mensuelles (€/L)**")
            # Préparation données pour le chart
            chart_data = df_avg.copy()
            chart_data["date"] = chart_data["date"].dt.strftime("%Y-%m")
            st.line_chart(chart_data.set_index("date")[["gasoil_routier", "gasoil_chauffage"]])
            
            # Tableau
            with st.expander("🔍 Voir le tableau complet des moyennes"):
                df_avg_disp = df_avg.copy()
                df_avg_disp["date"] = df_avg_disp["date"].dt.strftime("%B %Y")
                st.dataframe(df_avg_disp, use_container_width=True, hide_index=True)
        else:
            st.warning("⚠️ Impossible de charger les moyennes mensuelles. Assurez-vous que 'data/fuel_avg.csv' existe.")


else:
    st.error("❌ Aucune donnée récupérée. Le site est peut-être temporairement indisponible.")

# ── Calculateur coût trajet ───────────────────────────────────
st.markdown("<br>", unsafe_allow_html=True)
st.markdown("""
<div class="info-box">
    🧮 <strong>Calculateur coût carburant par trajet</strong>
</div>
""", unsafe_allow_html=True)

cc1, cc2, cc3 = st.columns(3)

with cc1:
    distance_km = st.number_input("Distance (km)", min_value=0, value=500, step=10)
with cc2:
    conso_100 = st.number_input("Consommation (L/100km)", min_value=0.0, value=32.0, step=0.5)
with cc3:
    if not df.empty and "diesel_routier" in df["type"].values:
        default_price = df[df["type"] == "diesel_routier"].iloc[-1]["prix"]
    elif "prices" in tarif and tarif["prices"]:
        default_price = list(tarif["prices"].values())[0]
    else:
        default_price = 1.70
    prix_litre = st.number_input("Prix gasoil (€/L)", min_value=0.0, value=round(default_price, 4), step=0.01, format="%.4f")

litres_needed = (distance_km / 100) * conso_100
cout_total    = litres_needed * prix_litre
cout_par_km   = cout_total / distance_km if distance_km > 0 else 0

r1, r2, r3 = st.columns(3)
with r1:
    st.markdown(f"""
    <div class="price-card">
        <div class="label">Litres nécessaires</div>
        <div class="price" style="font-size:2rem">{litres_needed:.1f}L</div>
    </div>""", unsafe_allow_html=True)
with r2:
    st.markdown(f"""
    <div class="price-card">
        <div class="label">Coût total</div>
        <div class="price" style="font-size:2rem;color:#F39C12">{cout_total:.2f}€</div>
    </div>""", unsafe_allow_html=True)
with r3:
    st.markdown(f"""
    <div class="price-card">
        <div class="label">Coût / km</div>
        <div class="price" style="font-size:2rem;color:#4A90D9">{cout_par_km:.4f}€</div>
    </div>""", unsafe_allow_html=True)

# ── Source ────────────────────────────────────────────────────
st.markdown("""
<br>
<div style="text-align:center">
    <span class="source-badge">
        📡 Source : SPF Economie — economie.fgov.be
    </span>
</div>
""", unsafe_allow_html=True)
