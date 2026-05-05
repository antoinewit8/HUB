# ── Tableau consolidé (sans KM pour l'instant) ────────────
    st.markdown("### 📋 Tableau consolidé")

    # ── Listes des valeurs disponibles pour les filtres ──
    chauffeurs_dispo = sorted([
        c for c in df_cons_f["chauffeur"].dropna().unique()
        if c and c != "nan"
    ])
    remorques_dispo = sorted([
        str(r).strip() for r in df_cons_f["remorque"].dropna().unique()
        if str(r).strip() and str(r).strip() not in ("nan", "")
    ]) if "remorque" in df_cons_f.columns else []

    tracteurs_dispo = sorted([
        str(t).strip() for t in df_cons_f["tracteur"].dropna().unique()
        if str(t).strip() and str(t).strip() not in ("nan", "")
    ]) if "tracteur" in df_cons_f.columns else []

    # ── Filtres ──
    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        filtre_chauffeur = st.multiselect(
            "🚛 Filtrer par chauffeur :",
            options=chauffeurs_dispo,
            default=[],
            placeholder="Tous les chauffeurs",
        )
    with fc2:
        filtre_remorque = st.multiselect(
            "🔗 Filtrer par remorque :",
            options=remorques_dispo,
            default=[],
            placeholder="Toutes les remorques",
        )
    with fc3:
        filtre_tracteur = st.multiselect(
            "🚜 Filtrer par tracteur :",
            options=tracteurs_dispo,
            default=[],
            placeholder="Tous les tracteurs",
        )

    # ── Application des filtres ──
    df_display = df_cons_f.copy()
    if filtre_chauffeur:
        df_display = df_display[df_display["chauffeur"].isin(filtre_chauffeur)]
    if filtre_remorque and "remorque" in df_display.columns:
        df_display = df_display[df_display["remorque"].isin(filtre_remorque)]
    if filtre_tracteur and "tracteur" in df_display.columns:
        df_display = df_display[df_display["tracteur"].isin(filtre_tracteur)]

    # ── KPIs de la sélection (si au moins un filtre actif) ──
    if filtre_chauffeur or filtre_remorque or filtre_tracteur:
        _sel_label = []
        if filtre_chauffeur:
            _sel_label.append(f"{len(filtre_chauffeur)} chauffeur(s)")
        if filtre_remorque:
            _sel_label.append(f"{len(filtre_remorque)} remorque(s)")
        if filtre_tracteur:
            _sel_label.append(f"{len(filtre_tracteur)} tracteur(s)")
        st.markdown(f"##### 📊 Aperçu — {', '.join(_sel_label)}")

        fk1, fk2, fk3, fk4, fk5, fk6 = st.columns(6)
        _tv = df_display["total_vente"].sum()
        _pt = df_display["prix_transport"].sum()
        _nd = len(df_display)
        fk1.metric("📁 Dossiers",       _nd)
        fk2.metric("📍 Stops",          int(df_display["nb_stops"].sum()))
        fk3.metric("💶 Prix Transport", f"{_pt:,.0f} €")
        fk4.metric("💶 Total Ventes",   f"{_tv:,.0f} €")
        fk5.metric("📈 CA moy/dossier", f"{(_tv / _nd if _nd else 0):,.0f} €")

        if "df_result" in st.session_state:
            _dr_f = st.session_state["df_result"].copy()
            if filtre_chauffeur:
                _dr_f = _dr_f[_dr_f["chauffeur"].isin(filtre_chauffeur)]
            if filtre_remorque and "remorque" in _dr_f.columns:
                _dr_f = _dr_f[_dr_f["remorque"].isin(filtre_remorque)]
            if filtre_tracteur and "tracteur" in _dr_f.columns:
                _dr_f = _dr_f[_dr_f["tracteur"].isin(filtre_tracteur)]
            _km = _dr_f["km_total"].sum()
            _rent = _dr_f["total_vente"].sum() / _km if _km > 0 else 0
            fk6.metric("⚡ Rentabilité", f"{_rent:.2f} €/km")
        else:
            fk6.metric("⚡ Rentabilité", "— (après PTV)")

    # ── Tableau ──
    cols_show = [
        "dossier", "chauffeur", "tracteur", "remorque",
        "date_debut", "date_fin", "client", "etat_vente",
        "nb_stops", "stops_texte", "prix_transport", "total_vente",
    ]
    st.dataframe(
        df_display[[c for c in cols_show if c in df_display.columns]].rename(columns={
            "dossier":        "N° Dossier",
            "chauffeur":      "Chauffeur",
            "tracteur":       "Tracteur",
            "remorque":       "Remorque",
            "date_debut":     "Date début",
            "date_fin":       "Date fin",
            "client":         "Client",
            "etat_vente":     "État vente",
            "nb_stops":       "Nb stops",
            "stops_texte":    "Séquence stops",
            "prix_transport": "Prix Transport (€)",
            "total_vente":    "Total Vente (€)",
        }),
        use_container_width=True,
        height=400,
    )

    st.divider()

    # ══════════════════════════════════════════════════════════
    #  CALCUL KM via PTV
    # ══════════════════════════════════════════════════════════
    st.markdown("### 🗺️ Calcul KM via PTV")

    ptv_c1, ptv_c2, ptv_c3 = st.columns(3)
    with ptv_c1:
        chauffeurs_ptv = st.multiselect(
            "🚛 Chauffeurs :",
            options=chauffeurs_dispo,
            default=[],
            placeholder="Sélectionner des chauffeurs...",
        )
    with ptv_c2:
        remorques_ptv = st.multiselect(
            "🔗 Remorques :",
            options=remorques_dispo,
            default=[],
            placeholder="Toutes les remorques",
        )
    with ptv_c3:
        tracteurs_ptv = st.multiselect(
            "🚜 Tracteurs :",
            options=tracteurs_dispo,
            default=[],
            placeholder="Tous les tracteurs",
        )

    # ── Construire la liste des chauffeurs à calculer ──
    # Partir des chauffeurs explicitement sélectionnés,
    # puis ajouter ceux liés aux remorques / tracteurs choisis.
    chauffeurs_a_calculer = list(chauffeurs_ptv)

    if remorques_ptv and "remorque" in df_cons_f.columns:
        ch_remorque = (
            df_cons_f[df_cons_f["remorque"].isin(remorques_ptv)]["chauffeur"]
            .dropna()
            .unique()
            .tolist()
        )
        chauffeurs_a_calculer = list(set(chauffeurs_a_calculer + ch_remorque))

    if tracteurs_ptv and "tracteur" in df_cons_f.columns:
        ch_tracteur = (
            df_cons_f[df_cons_f["tracteur"].isin(tracteurs_ptv)]["chauffeur"]
            .dropna()
            .unique()
            .tolist()
        )
        chauffeurs_a_calculer = list(set(chauffeurs_a_calculer + ch_tracteur))

    nb_dossiers_ptv = len(df_cons_f[df_cons_f["chauffeur"].isin(chauffeurs_a_calculer)])
    if chauffeurs_a_calculer:
        extras = []
        if remorques_ptv:
            extras.append(f"{len(remorques_ptv)} remorque(s)")
        if tracteurs_ptv:
            extras.append(f"{len(tracteurs_ptv)} tracteur(s)")
        extras_str = f", {', '.join(extras)}" if extras else ""
        st.info(
            f"ℹ️ Calcul pour **{nb_dossiers_ptv} dossiers** "
            f"({len(chauffeurs_a_calculer)} chauffeur(s){extras_str})."
        )

    btn_ptv = st.button(
        "🚀 Lancer le calcul PTV",
        disabled=(not chauffeurs_a_calculer),
        type="primary",
    )
