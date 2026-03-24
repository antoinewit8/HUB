# core/exporter.py

import pandas as pd
from openpyxl.styles import PatternFill, Font, Alignment
from openpyxl.utils import get_column_letter

def export_to_excel(empty_km_list, friday_data, output_path="outputs/rapport_camion.xlsx"):
    
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:

        # ========== FEUILLE 1 : KM À VIDE ==========
        df_vide = pd.DataFrame(empty_km_list)
        df_vide.columns = ["Date départ", "Date arrivée", "Ville départ", "Ville arrivée", "KM à vide"]
        df_vide.to_excel(writer, sheet_name="KM à vide", index=False)

        ws1 = writer.sheets["KM à vide"]

        # Header rouge
        header_fill = PatternFill("solid", fgColor="C00000")
        header_font = Font(bold=True, color="FFFFFF")

        for col in range(1, 6):
            cell = ws1.cell(row=1, column=col)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center")

        # Colorier les lignes avec km élevés (> 200)
        orange_fill = PatternFill("solid", fgColor="FFD966")
        red_fill = PatternFill("solid", fgColor="FF7070")

        for row_idx, entry in enumerate(empty_km_list, start=2):
            km = entry["km_vide"]
            if km > 300:
                fill = red_fill
            elif km > 200:
                fill = orange_fill
            else:
                fill = None

            if fill:
                for col in range(1, 6):
                    ws1.cell(row=row_idx, column=col).fill = fill

        # Largeur colonnes auto
        for col in range(1, 6):
            ws1.column_dimensions[get_column_letter(col)].width = 30

        # Ligne total
        total = sum(e["km_vide"] for e in empty_km_list)
        last_row = len(empty_km_list) + 2
        ws1.cell(row=last_row, column=4).value = "TOTAL KM À VIDE"
        ws1.cell(row=last_row, column=4).font = Font(bold=True)
        ws1.cell(row=last_row, column=5).value = total
        ws1.cell(row=last_row, column=5).font = Font(bold=True)


        # ========== FEUILLE 2 : VENDREDIS ==========
             rows_friday = []
        for f in friday_data:
            rows_friday.append({
                "Date": f["date"],
                "KM parcourus": f["km_parcourus"],
                "Nb activités": f["nb_activites"],
                "Heure de fin": f["heure_fin"],
                "Villes visitées": " → ".join(f["villes_visitees"]),
                "Statut": "🔴 ALERTE" if f["alerte"] else "✅ Normal",
                "Raisons": " | ".join(f["raisons"]) if f["raisons"] else ""
            })

        df_friday = pd.DataFrame(rows_friday)
        df_friday.to_excel(writer, sheet_name="Vendredis", index=False)

        ws2 = writer.sheets["Vendredis"]

        # Header
        for col in range(1, 5):
            cell = ws2.cell(row=1, column=col)
            cell.fill = PatternFill("solid", fgColor="1F3864")
            cell.font = Font(bold=True, color="FFFFFF")
            cell.alignment = Alignment(horizontal="center")

        # Colorier alertes
        for row_idx, f in enumerate(friday_data, start=2):
            if f["alerte"]:
                for col in range(1, 5):
                    ws2.cell(row=row_idx, column=col).fill = PatternFill("solid", fgColor="FF7070")

        # Largeur colonnes
        ws2.column_dimensions["A"].width = 15
        ws2.column_dimensions["B"].width = 15
        ws2.column_dimensions["C"].width = 60
        ws2.column_dimensions["D"].width = 15

    print(f"\n✅ Rapport exporté : {output_path}")
