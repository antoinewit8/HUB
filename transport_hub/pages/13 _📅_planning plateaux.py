@st.fragment
def render_pays_carte(points, arcs_draw, agg, pays_total, pays_detail,
                      pays_rows, show_mode, focus_norm, legs, dmap, MAX_GEO):

    val_color = "#4a8abf" if show_mode == "Déchargements" else "#cdd4ea" if show_mode == "Les deux" else "#4abf6a"
    title_mode = {"Les deux": "Tous", "Chargements": "Charg.", "Déchargements": "Déch."}[show_mode]

    if "pp_selected_pays" not in st.session_state:
        st.session_state["pp_selected_pays"] = None

    col_panel, col_map = st.columns([1, 5])

    with col_panel:
        st.markdown(
            f'<div style="font-size:.58rem;font-weight:700;letter-spacing:2.5px;'
            f'text-transform:uppercase;color:#3a4258;margin-bottom:.5rem;'
            f'font-family:\'Barlow Condensed\',sans-serif;">🚛 Camions · {title_mode}</div>',
            unsafe_allow_html=True)

        pays_order = sorted(pays_total.keys(), key=lambda k: -pays_total[k])

        for pays_code in pays_order:
            total     = pays_total[pays_code]
            flag      = PAYS_FLAGS.get(pays_code, "🏳️")
            details   = pays_detail.get(pays_code, [])
            is_active = st.session_state["pp_selected_pays"] == pays_code

            detail_html = ""
            if details:
                parts = [f"+{n} {loc}" for loc, n in details[:4]]
                detail_html = '<div class="pp-detail-line">⤷ ' + "  ·  ".join(parts) + '</div>'

            active_style = (
                f"border-color:{val_color};background:#1a2b1f;"
                f"box-shadow:0 0 0 1px {val_color}33;"
            ) if is_active else ""

            st.markdown(f"""
<div class="pp-card-btn" style="{active_style};margin-bottom:0;">
  <div class="pp-row-top">
    <span class="pp-flag">{flag}</span>
    <span class="pp-code">{pays_code}</span>
    <span style="font-family:'Barlow Condensed',sans-serif;font-size:2.4rem;font-weight:800;color:{val_color};line-height:1;margin-left:auto;">{total}</span>
  </div>
  {detail_html}
</div>""", unsafe_allow_html=True)

            btn_label = "✕ Fermer" if is_active else "📋 Détails"
            btn_type  = "primary" if is_active else "secondary"

            if st.button(btn_label, key=f"pp_btn_{pays_code}",
                         use_container_width=True, type=btn_type):
                st.session_state["pp_selected_pays"] = (None if is_active else pays_code)
                st.rerun(scope="fragment")

    # ── Filtre carte selon pays sélectionné ───────────────────────────────
    sel_pays = st.session_state.get("pp_selected_pays")
    if sel_pays:
        points_map = [p for p in points if p.get("pays_logi", p.get("pays")) == sel_pays]
        locs_sel   = {p["loc_norm"] for p in points_map}
        arcs_map   = [a for a in arcs_draw if a["cn"] in locs_sel or a["dn"] in locs_sel]
    else:
        points_map = points
        arcs_map   = arcs_draw

    with col_map:
        try:
            import pydeck as pdk
            dfp = pd.DataFrame(points_map)
            layers = [
                pdk.Layer("ScatterplotLayer", data=dfp, id="pts",
                          get_position="[lon, lat]", get_radius="radius",
                          radius_min_pixels=8, radius_max_pixels=48,
                          get_fill_color="color", get_line_color=[255,255,255,110],
                          stroked=True, line_width_min_pixels=1, pickable=True,
                          auto_highlight=True),
                pdk.Layer("TextLayer", data=dfp, get_position="[lon, lat]",
                          get_text="label", get_size=14, get_color=[10,14,18,255],
                          get_anchor="middle", get_alignment_baseline="'center'", font_weight=800),
                pdk.Layer("TextLayer", data=dfp, get_position="[lon, lat]",
                          get_text="nom", get_size=11, get_color=[200,210,230,210],
                          get_anchor="middle", get_alignment_baseline="'bottom'",
                          get_pixel_offset=[0,-16]),
            ]
            if arcs_map:
                layers.insert(0, pdk.Layer("ArcLayer", data=pd.DataFrame(arcs_map),
                    get_source_position="[sl, sla]", get_target_position="[tl, tla]",
                    get_source_color=[74,191,106,150], get_target_color=[74,138,191,170],
                    get_width="w", width_min_pixels=1))
            zoom_level = 6 if sel_pays else 5
            deck = pdk.Deck(
                layers=layers,
                initial_view_state=pdk.ViewState(
                    latitude=dfp["lat"].mean(),
                    longitude=dfp["lon"].mean(),
                    zoom=zoom_level, pitch=25),
                tooltip={"html": "<b>{nom}</b><br>{typ} · <b>{camions}</b> dossier(s)<br>"
                                 "<span style='color:#8a93ad'>Dossiers : {dossiers}</span>",
                         "style": {"background":"#141821","color":"#cdd4ea",
                                   "font-family":"Barlow Condensed, sans-serif","padding":"9px"}},
                map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
            )
            map_key = f"planmap_{sel_pays or 'all'}"
            try:
                st.pydeck_chart(deck, use_container_width=True, height=680,
                                key=map_key, selection_mode="single-object", on_select="rerun")
            except TypeError:
                st.pydeck_chart(deck, use_container_width=True, height=680)
            if len(agg) >= MAX_GEO and not focus_norm:
                st.caption(f"Géocodage limité aux {MAX_GEO} lieux les plus actifs.")
        except ImportError:
            st.map(pd.DataFrame(points_map).rename(columns={"lat":"latitude","lon":"longitude"}))

    # ── Détail pays pleine largeur ─────────────────────────────────────────
    if sel_pays and sel_pays in pays_rows:
        flag_s = PAYS_FLAGS.get(sel_pays, "🏳️")
        rows_sel = pays_rows[sel_pays]
        detail_records = []
        for row in rows_sel:
            dos = row["dossier"]
            lg  = legs.get(dos, {})
            detail_records.append({
                "N° Dossier":  dos,
                "Type":        "Chargement" if row["type"] == "C" else (
                               "Déchargement" if row["type"] == "D" else "?"),
                "Date":        row["date"].strftime("%d/%m/%Y") if pd.notna(row["date"]) else "—",
                "Heure":       row["heure"] or "—",
                "Localité":    row["localite"] or "—",
                "Chauffeur":   row["chauffeur"] or "—",
                "Tracteur":    row["immat"] or "—",
                "Remorque":    row["remorque"] or "—",
                "Flotte":      "TRA" if row["is_tra"] else "CB",
                "Charg. →":    lg.get("c_loc", "—"),
                "→ Déch.":     lg.get("d_loc", "—"),
            })
        df_detail = pd.DataFrame(detail_records).sort_values(["Date", "Heure", "N° Dossier"])
        n_dos = df_detail["N° Dossier"].nunique()
        st.markdown(
            f'<div class="sect">{flag_s} Détail {sel_pays} '
            f'<span class="hint">{n_dos} dossiers · {len(df_detail)} activités</span></div>',
            unsafe_allow_html=True)
        st.dataframe(df_detail, hide_index=True, use_container_width=True,
                     height=min(420, 38 + len(df_detail) * 36))
