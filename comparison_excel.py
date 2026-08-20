"""
comparison_excel.py
Builds an executive-grade comparison workbook for the Playbet quarterly comparison.

Structure:
  • "Overview" cover sheet — branded banner, scope, headline KPIs, and the key findings
    (busiest/least-busy month, best/worst value month, biggest riser & faller).
  • One sheet per analysis — branded banner, subtitle, a formatted table with a bold
    TOTAL row where meaningful, zebra striping, conditional colour on change/rank columns.

No charts (removed by request). Professional Arial throughout. Returns bytes.
"""

from io import BytesIO
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side, NamedStyle
from openpyxl.utils import get_column_letter

# --- palette (Playbet slate + emerald, matching the dashboard) ---
NAVY      = "0F172A"   # slate-900 banner
SLATE     = "1F3864"
EMERALD   = "10B981"
EMERALD_D = "059669"
GREY_HEAD = "334155"   # table header
ZEBRA     = "F1F5F9"   # light row stripe
POS_GREEN = "16A34A"
NEG_RED   = "C0392B"
AMBER     = "F59E0B"
TEXT_DARK = "0F172A"
TEXT_MUTE = "64748B"

WHITE = "FFFFFF"
THIN  = Side(style="thin", color="D9E2EC")
MED   = Side(style="medium", color=SLATE)

F_TITLE   = Font(name="Arial", size=20, bold=True, color=WHITE)
F_SUBTLE  = Font(name="Arial", size=10, color="CBD5E1")
F_BANNER  = Font(name="Arial", size=14, bold=True, color=WHITE)
F_SUBHEAD = Font(name="Arial", size=10, italic=True, color=TEXT_MUTE)
F_HEAD    = Font(name="Arial", size=10, bold=True, color=WHITE)
F_BASE    = Font(name="Arial", size=10, color=TEXT_DARK)
F_BOLD    = Font(name="Arial", size=10, bold=True, color=TEXT_DARK)
F_KPI_LBL = Font(name="Arial", size=9,  bold=True, color=TEXT_MUTE)
F_KPI_VAL = Font(name="Arial", size=18, bold=True, color=SLATE)
F_FIND    = Font(name="Arial", size=11, bold=True, color=TEXT_DARK)
F_FIND_L  = Font(name="Arial", size=9,  bold=True, color=EMERALD_D)

FILL_NAVY    = PatternFill("solid", fgColor=NAVY)
FILL_BANNER  = PatternFill("solid", fgColor=SLATE)
FILL_HEAD    = PatternFill("solid", fgColor=GREY_HEAD)
FILL_ZEBRA   = PatternFill("solid", fgColor=ZEBRA)
FILL_EMERALD = PatternFill("solid", fgColor=EMERALD)
FILL_TOTAL   = PatternFill("solid", fgColor="E2E8F0")
FILL_KPI     = PatternFill("solid", fgColor="F8FAFC")

CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
LEFT   = Alignment(horizontal="left", vertical="center")
RIGHT  = Alignment(horizontal="right", vertical="center")


def _is_pct(colname):
    c = str(colname)
    return "%" in c or "GWM" in c


def _is_money(colname):
    c = str(colname).lower()
    return any(k in c for k in ("paid in", "gross win", "paid out", "net win", "value"))


def _banner(ws, ncols, title, subtitle):
    """Slate banner across the table width + italic subtitle line."""
    last = get_column_letter(max(ncols, 3))
    ws.merge_cells(f"A1:{last}1")
    ws["A1"] = title
    ws["A1"].font = F_BANNER
    ws["A1"].fill = FILL_BANNER
    ws["A1"].alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[1].height = 30
    ws.merge_cells(f"A2:{last}2")
    ws["A2"] = subtitle
    ws["A2"].font = F_SUBHEAD
    ws["A2"].alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[2].height = 18


def _write_table(ws, df, start_row, total_row=True, rank_cols=None, change_cols=None):
    """Write a styled table. Returns the row after the table."""
    rank_cols = rank_cols or []
    change_cols = change_cols or []
    ncols = len(df.columns)

    # header
    hr = start_row
    for j, col in enumerate(df.columns, start=1):
        c = ws.cell(row=hr, column=j, value=str(col))
        c.font = F_HEAD
        c.fill = FILL_HEAD
        c.alignment = CENTER
        c.border = Border(left=THIN, right=THIN, top=MED, bottom=MED)
    ws.row_dimensions[hr].height = 26

    # body
    r = hr + 1
    for i, (_, row) in enumerate(df.iterrows()):
        zebra = (i % 2 == 1)
        for j, (col, val) in enumerate(zip(df.columns, row), start=1):
            v = val.item() if hasattr(val, "item") else val
            if pd.isna(v):
                v = ""
            cell = ws.cell(row=r, column=j, value=v)
            cell.font = F_BASE
            cell.border = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
            if zebra:
                cell.fill = FILL_ZEBRA
            # alignment + number format
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                cell.alignment = RIGHT
                if _is_pct(col):
                    cell.number_format = '0.00"%"'
                elif _is_money(col):
                    cell.number_format = 'R #,##0.00'
                else:
                    cell.number_format = "#,##0"
            else:
                cell.alignment = LEFT
            # conditional colour on change columns
            if col in change_cols and isinstance(v, (int, float)):
                if v > 0:
                    cell.font = Font(name="Arial", size=10, bold=True, color=POS_GREEN)
                elif v < 0:
                    cell.font = Font(name="Arial", size=10, bold=True, color=NEG_RED)
            # colour the rank/flag text columns
            if col in rank_cols and isinstance(v, str) and v:
                low = v.lower()
                if "busiest" in low or "best" in low or "increase" in low:
                    cell.font = Font(name="Arial", size=10, bold=True, color=EMERALD_D)
                elif "least" in low or "worst" in low or "decrease" in low:
                    cell.font = Font(name="Arial", size=10, bold=True, color=NEG_RED)
        r += 1

    # TOTAL row (numeric columns only, first column labelled TOTAL)
    if total_row and len(df) > 0:
        numeric_cols = [c for c in df.columns
                        if pd.api.types.is_numeric_dtype(df[c]) and not _is_pct(c)]
        if numeric_cols:
            for j, col in enumerate(df.columns, start=1):
                cell = ws.cell(row=r, column=j)
                cell.fill = FILL_TOTAL
                cell.border = Border(left=THIN, right=THIN, top=MED, bottom=MED)
                if j == 1:
                    cell.value = "TOTAL"
                    cell.font = F_BOLD
                    cell.alignment = LEFT
                elif col in numeric_cols:
                    col_letter = get_column_letter(j)
                    cell.value = f"=SUM({col_letter}{hr+1}:{col_letter}{r-1})"
                    cell.font = F_BOLD
                    cell.alignment = RIGHT
                    cell.number_format = 'R #,##0.00' if _is_money(col) else "#,##0"
            r += 1

    # widths
    for j, col in enumerate(df.columns, start=1):
        vals = [str(col)] + [str(v) for v in df.iloc[:, j - 1].tolist()]
        width = min(max(len(x) for x in vals) + 3, 40)
        ws.column_dimensions[get_column_letter(j)].width = max(width, 11)

    ws.freeze_panes = ws.cell(row=hr + 1, column=1)
    ws.sheet_view.showGridLines = False
    return r + 1


def _sheet(wb, tab, df, title, subtitle, total_row=True, rank_cols=None, change_cols=None):
    ws = wb.create_sheet(title=tab[:31])
    _banner(ws, len(df.columns), title, subtitle)
    _write_table(ws, df, start_row=4, total_row=total_row,
                 rank_cols=rank_cols, change_cols=change_cols)
    return ws


def _overview(wb, meta, kpis, findings):
    ws = wb.create_sheet(title="Overview")
    ws.sheet_view.showGridLines = False
    # brand banner
    ws.merge_cells("A1:F2")
    ws["A1"] = "PLAYBET"
    ws["A1"].font = Font(name="Arial", size=26, bold=True, color=WHITE)
    ws["A1"].fill = FILL_NAVY
    ws["A1"].alignment = Alignment(horizontal="left", vertical="center", indent=1)
    for r in (1, 2):
        for c in range(1, 7):
            ws.cell(row=r, column=c).fill = FILL_NAVY
    ws.row_dimensions[1].height = 26
    ws.row_dimensions[2].height = 20
    ws.merge_cells("A3:F3")
    ws["A3"] = "Quarterly Performance Comparison"
    ws["A3"].font = Font(name="Arial", size=15, bold=True, color=SLATE)
    ws.merge_cells("A4:F4")
    ws["A4"] = meta
    ws["A4"].font = F_SUBHEAD

    # KPI cards row
    row = 6
    ws.merge_cells(f"A{row}:F{row}")
    ws[f"A{row}"] = "HEADLINE FIGURES"
    ws[f"A{row}"].font = F_KPI_LBL
    row += 1
    col = 1
    for label, value in kpis.items():
        ws.merge_cells(start_row=row, start_column=col, end_row=row, end_column=col + 1)
        lc = ws.cell(row=row, column=col, value=label)
        lc.font = F_KPI_LBL
        lc.fill = FILL_KPI
        lc.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        ws.merge_cells(start_row=row + 1, start_column=col, end_row=row + 1, end_column=col + 1)
        vc = ws.cell(row=row + 1, column=col, value=value)
        vc.font = F_KPI_VAL
        vc.fill = FILL_KPI
        vc.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        for rr in (row, row + 1):
            for cc in (col, col + 1):
                ws.cell(row=rr, column=cc).border = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
        col += 2
        if col > 5:
            col = 1
            row += 3
    row += 3

    # Key findings
    ws.merge_cells(f"A{row}:F{row}")
    fh = ws.cell(row=row, column=1, value="KEY FINDINGS")
    fh.font = F_BANNER
    fh.fill = FILL_BANNER
    fh.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[row].height = 26
    row += 2
    for label, text in findings:
        lc = ws.cell(row=row, column=1, value=label)
        lc.font = F_FIND_L
        lc.alignment = Alignment(horizontal="left", vertical="top", indent=1)
        ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=6)
        tc = ws.cell(row=row, column=2, value=text)
        tc.font = F_BASE
        tc.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
        ws.row_dimensions[row].height = 30
        row += 1

    ws.column_dimensions["A"].width = 22
    for c in "BCDEF":
        ws.column_dimensions[c].width = 20
    return ws


def _fmt_money(x):
    try:
        return f"R {x:,.0f}"
    except Exception:
        return str(x)


def build_comparison_workbook(tables: dict, meta: str) -> bytes:
    wb = Workbook()
    wb.remove(wb.active)

    bw   = tables.get("Best-Worst Month", pd.DataFrame())
    gid  = tables.get("Games Increase-Decrease", pd.DataFrame())
    gbm  = tables.get("Games Betslips by Month", pd.DataFrame())
    cbm  = tables.get("Cashier Betslips by Month", pd.DataFrame())

    # ---- derive headline KPIs + findings for the Overview ----
    kpis = {}
    findings = []
    if not bw.empty:
        if "Betslips" in bw.columns:
            kpis["Total Betslips"] = int(bw["Betslips"].sum())
        if "Paid In" in bw.columns:
            kpis["Total Paid In"] = _fmt_money(bw["Paid In"].sum())
        if "Gross Win" in bw.columns:
            kpis["Total Gross Win"] = _fmt_money(bw["Gross Win"].sum())
        if "Volume" in bw.columns:
            busiest = bw.loc[bw["Volume"] == "Busiest", "Month"]
            quiet   = bw.loc[bw["Volume"] == "Least busy", "Month"]
            if len(busiest):
                findings.append(("BUSIEST", f"{busiest.iloc[0]} had the highest betslip volume in the quarter."))
            if len(quiet):
                findings.append(("QUIETEST", f"{quiet.iloc[0]} had the lowest betslip volume in the quarter."))
        if "Value" in bw.columns:
            best  = bw.loc[bw["Value"] == "Best value", "Month"]
            worst = bw.loc[bw["Value"] == "Worst value", "Month"]
            if len(best):
                findings.append(("BEST VALUE", f"{best.iloc[0]} produced the most gross win (best value month)."))
            if len(worst):
                findings.append(("WORST VALUE", f"{worst.iloc[0]} produced the least gross win (worst value month)."))
    if not gid.empty and "Change in Betslips" in gid.columns:
        top = gid.iloc[0]
        bottom = gid.iloc[-1]
        findings.append(("TOP RISER", f"{top['Game']} rose {int(top['Change in Betslips']):+,} betslips ({top['Change (%)']:+.1f}%) from first to last month."))
        if bottom["Change in Betslips"] < 0:
            findings.append(("TOP FALLER", f"{bottom['Game']} fell {int(bottom['Change in Betslips']):+,} betslips ({bottom['Change (%)']:+.1f}%) over the quarter."))
    if not gbm.empty:
        kpis.setdefault("Games Tracked", len(gbm))
    if not cbm.empty:
        kpis.setdefault("Cashiers Tracked", len(cbm))

    _overview(wb, meta, kpis, findings)

    # ---- analysis sheets ----
    SPECS = [
        ("Best-Worst Month", "Best-Worst Month",
         "Busiest & Least-Busy Month · Best & Worst Value Month",
         "Busiest/least-busy ranked by betslip volume; best/worst by gross win. " + meta,
         False, ["Volume", "Value"], []),
        ("Games Betslips by Month", "Games Betslips by Month",
         "Games — Betslip Count by Month",
         "Each game's betslips side-by-side across the quarter's three months. " + meta,
         True, [], []),
        ("Games Increase-Decrease", "Games Increase-Decrease",
         "Games — Betslip Increase / Decrease",
         "First month vs last month; green = growth, red = decline. " + meta,
         False, ["Trend"], ["Change in Betslips", "Change (%)"]),
        ("Games per Branch", "Games per Branch",
         "Games per Branch",
         "Betslips, Paid In, Gross Win and Gross Win Margin % per game, per branch. " + meta,
         False, [], []),
        ("Games GWM", "Games GWM",
         "Games — Gross Win Margin %",
         "Gross Win Margin % = Gross Win ÷ Paid In, by month and for the whole quarter. " + meta,
         False, [], []),
        ("Cashier Betslips by Month", "Cashier Betslips by Month",
         "Cashiers — Betslip Count by Month",
         "Each cashier's betslips side-by-side across the quarter. " + meta,
         True, [], []),
        ("Cashier GWM", "Cashier GWM",
         "Cashiers — Gross Win Margin %",
         "Per-month GW Margin %; quarter column is paid-in weighted. " + meta,
         False, [], []),
    ]
    for key, tab, title, subtitle, total_row, rank_cols, change_cols in SPECS:
        df = tables.get(key)
        if df is None or df.empty:
            continue
        _sheet(wb, tab, df, title, subtitle,
               total_row=total_row, rank_cols=rank_cols, change_cols=change_cols)

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()
