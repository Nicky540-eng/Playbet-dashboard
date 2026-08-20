"""
comparison.py
Quarter-based comparison analytics for the Playbet dashboard.

Consumes the two full-detail frames loaded from Neon:
  slip_df  columns: Shop, Cashier, BetSlips, PaidIn, PaidOut, GWMargin, NetWin, Year, Month, MonthNum
  game_df  columns: Shop, Game, BetSlips(=PaidInCount), PaidIn, PaidOutCount, PaidOut, GrossWin, Year, Month, MonthNum

A "quarter" is three calendar months of one year:
  Q1 Jan-Mar, Q2 Apr-Jun, Q3 Jul-Sep, Q4 Oct-Dec.
Everything is scoped to the (year, quarter) the user picks, and optionally one branch.
"""

import pandas as pd

MONTHS = ["January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December"]

QUARTERS = {
    "Q1 (Jan–Mar)": [1, 2, 3],
    "Q2 (Apr–Jun)": [4, 5, 6],
    "Q3 (Jul–Sep)": [7, 8, 9],
    "Q4 (Oct–Dec)": [10, 11, 12],
}


def scope(df, year, quarter_label, branch=None):
    """Filter a frame to one year+quarter (+ optional branch)."""
    if df is None or df.empty:
        return df
    months = QUARTERS[quarter_label]
    out = df[(df["Year"].astype(str) == str(year)) & (df["MonthNum"].isin(months))]
    if branch and branch != "All Branches":
        out = out[out["Shop"] == branch]
    return out.copy()


def _month_cols(months):
    return [MONTHS[m - 1] for m in months]


# ---------------------------------------------------------------------------
# GAMES
# ---------------------------------------------------------------------------

def games_betslip_h2h(game_df, quarter_label):
    """Betslip count per game, one column per month of the quarter."""
    if game_df is None or game_df.empty:
        return pd.DataFrame()
    months = QUARTERS[quarter_label]
    piv = (game_df.groupby(["Game", "MonthNum"])["BetSlips"].sum()
                  .unstack("MonthNum").reindex(columns=months).fillna(0).astype(int))
    piv.columns = _month_cols(months)
    piv["Total"] = piv.sum(axis=1)
    piv.index.name = "Game"
    return piv.sort_values("Total", ascending=False).reset_index()


def games_increase_decrease(game_df, quarter_label):
    """First-month -> last-month betslip change per game across the quarter."""
    if game_df is None or game_df.empty:
        return pd.DataFrame()
    months = QUARTERS[quarter_label]
    piv = (game_df.groupby(["Game", "MonthNum"])["BetSlips"].sum()
                  .unstack("MonthNum").reindex(columns=months).fillna(0))
    first, last = months[0], months[-1]
    res = pd.DataFrame(index=piv.index)
    for m in months:
        res[MONTHS[m - 1]] = piv[m].astype(int)
    res["Change in Betslips"] = (piv[last] - piv[first]).astype(int)
    res["Change (%)"] = ((piv[last] - piv[first]) / piv[first].replace(0, float("nan")) * 100).round(1)
    res["Trend"] = res["Change in Betslips"].apply(lambda x: "increase" if x > 0 else ("decrease" if x < 0 else "flat"))
    res.index.name = "Game"
    return res.sort_values("Change in Betslips", ascending=False).reset_index()


def games_per_branch(game_df):
    """Betslips + gross win per game per branch, over the scoped quarter."""
    if game_df is None or game_df.empty:
        return pd.DataFrame()
    out = (game_df.groupby(["Shop", "Game"])
                  .agg(BetSlips=("BetSlips", "sum"),
                       PaidIn=("PaidIn", "sum"),
                       GrossWin=("GrossWin", "sum"))
                  .reset_index().rename(columns={"Shop": "Branch"}))
    out["Gross Win Margin %"] = (out["GrossWin"] / out["PaidIn"].replace(0, float("nan")) * 100).round(2)
    return out.sort_values(["Branch", "BetSlips"], ascending=[True, False])


def games_gwm(game_df, quarter_label):
    """GWM% per game per month + a combined quarter GWM%."""
    if game_df is None or game_df.empty:
        return pd.DataFrame()
    months = QUARTERS[quarter_label]
    g = (game_df.groupby(["Game", "MonthNum"])
                .agg(gw=("GrossWin", "sum"), pi=("PaidIn", "sum")).reset_index())
    g["gwm"] = (g["gw"] / g["pi"].replace(0, float("nan")) * 100).round(2)
    piv = g.pivot(index="Game", columns="MonthNum", values="gwm").reindex(columns=months)
    piv.columns = [f"Gross Win Margin % {MONTHS[m - 1]}" for m in months]
    comb = game_df.groupby("Game").agg(gw=("GrossWin", "sum"), pi=("PaidIn", "sum"))
    piv["Gross Win Margin % (Quarter)"] = (comb["gw"] / comb["pi"].replace(0, float("nan")) * 100).round(2)
    piv.index.name = "Game"
    return piv.reset_index()


# ---------------------------------------------------------------------------
# CASHIERS
# ---------------------------------------------------------------------------

def cashier_betslip_h2h(slip_df, quarter_label):
    """Betslip count per cashier, one column per month of the quarter."""
    if slip_df is None or slip_df.empty:
        return pd.DataFrame()
    months = QUARTERS[quarter_label]
    piv = (slip_df.pivot_table(index=["Cashier", "Shop"], columns="MonthNum",
                               values="BetSlips", aggfunc="sum")
                  .reindex(columns=months).fillna(0).astype(int))
    piv.columns = _month_cols(months)
    piv["Total"] = piv.sum(axis=1)
    out = piv.reset_index().rename(columns={"Shop": "Branch"})
    return out.sort_values("Total", ascending=False)


def cashier_gwm(slip_df, quarter_label):
    """Cashier GWM% per month + combined quarter GWM% (paid-in-weighted)."""
    if slip_df is None or slip_df.empty:
        return pd.DataFrame()
    months = QUARTERS[quarter_label]
    piv = (slip_df.pivot_table(index=["Cashier", "Shop"], columns="MonthNum",
                               values="GWMargin", aggfunc="mean").reindex(columns=months))
    piv.columns = [f"Gross Win Margin % {MONTHS[m - 1]}" for m in months]
    comb = slip_df.groupby(["Cashier", "Shop"]).agg(pi=("PaidIn", "sum"), po=("PaidOut", "sum"))
    comb["Gross Win Margin % (Quarter)"] = ((comb["pi"] + comb["po"]) / comb["pi"].replace(0, float("nan")) * 100).round(2)
    out = piv.join(comb["Gross Win Margin % (Quarter)"]).reset_index().rename(columns={"Shop": "Branch"})
    return out


# ---------------------------------------------------------------------------
# QUARTER BEST / WORST MONTH  (busiest & least busy by volume; best & worst by value)
# ---------------------------------------------------------------------------

def best_worst_month(slip_df, game_df, quarter_label):
    """One row per month of the quarter with betslip volume, paid-in and gross win,
    flagging busiest/least-busy (volume) and best/worst (value)."""
    months = QUARTERS[quarter_label]
    rows = []
    for m in months:
        row = {"Month": MONTHS[m - 1]}
        if slip_df is not None and not slip_df.empty:
            s = slip_df[slip_df["MonthNum"] == m]
            row["Betslips"] = int(s["BetSlips"].sum())
            row["Paid In"] = float(s["PaidIn"].sum())
        if game_df is not None and not game_df.empty:
            g = game_df[game_df["MonthNum"] == m]
            row["Gross Win"] = float(g["GrossWin"].sum())
        rows.append(row)
    df = pd.DataFrame(rows)
    if "Betslips" in df.columns and df["Betslips"].notna().any() and len(df) > 1:
        df["Volume"] = ""
        df.loc[df["Betslips"].idxmax(), "Volume"] = "Busiest"
        df.loc[df["Betslips"].idxmin(), "Volume"] = "Least busy"
    if "Gross Win" in df.columns and df["Gross Win"].notna().any() and len(df) > 1:
        df["Value"] = ""
        df.loc[df["Gross Win"].idxmax(), "Value"] = "Best value"
        df.loc[df["Gross Win"].idxmin(), "Value"] = "Worst value"
    return df


# ---------------------------------------------------------------------------
# "Games in 2024 no longer there" — drop from comparison only
# ---------------------------------------------------------------------------

def drop_discontinued_games(game_df, latest_year):
    """Remove games that existed in 2024 but are absent in the latest year present.
    Only affects the comparison frame passed in."""
    if game_df is None or game_df.empty or "2024" not in set(game_df["Year"].astype(str)):
        return game_df
    games_2024 = set(game_df[game_df["Year"].astype(str) == "2024"]["Game"])
    games_latest = set(game_df[game_df["Year"].astype(str) == str(latest_year)]["Game"])
    discontinued = games_2024 - games_latest
    if not discontinued:
        return game_df
    return game_df[~game_df["Game"].isin(discontinued)].copy()
