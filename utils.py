#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Apr 27 00:44:41 2026

@author: hamidi
"""

"""
utils.py — Fonctions utilitaires
TPI · Analyse Financière (Dash)
"""

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf


# ── BRENT ─────────────────────────────────────────────────────────────────────
def detect_oil_rallies(brent, threshold=0.15, window=60):
    """Détecte les périodes de hausse du Brent (seuil +15% sur 60j)."""
    prices   = brent.dropna()
    roll_ret = prices.pct_change(window)
    rallies, in_rally = [], False
    rally_start = peak_price = peak_date = None

    for date, val in roll_ret.items():
        price = prices.loc[date]
        if not in_rally:
            if pd.notna(val) and val >= threshold:
                idx         = max(0, prices.index.get_loc(date) - window)
                rally_start = prices.index[idx]
                in_rally, peak_price, peak_date = True, price, date
        else:
            if price > peak_price:
                peak_price, peak_date = price, date
            elif price < peak_price * 0.92:
                rallies.append((rally_start, peak_date))
                in_rally = False

    if in_rally and rally_start:
        rallies.append((rally_start, prices.index[-1]))
    return rallies


def add_oil_rectangles(fig, rallies, first_only=False):
    """Ajoute les zones bleues de hausse Brent sur un graphique Plotly."""
    for i, (s, e) in enumerate(rallies):
        fig.add_vrect(
            x0=str(s), x1=str(e),
            fillcolor='rgba(59,130,246,0.13)', line_width=0,
            annotation_text="↑ Brent" if (not first_only or i == 0) else "",
            annotation_position="top left",
            annotation_font_size=9, annotation_font_color='#93c5fd',
        )
    return fig


def calc_metriques_brent(prices, tickers, rallies):
    """
    Calcule le rendement cumulé et la volatilité annualisée
    sur l'ensemble des fenêtres de hausse Brent.
    """
    rdt_records = {}
    vol_records = {}

    for t in tickers:
        if t not in prices.columns:
            rdt_records[t] = np.nan
            vol_records[t] = np.nan
            continue

        px       = prices[t].dropna()
        cumret   = 1.0
        all_rets = []

        for s, e in rallies:
            window = px.loc[s:e].dropna()
            if len(window) < 2:
                continue
            cumret *= (window.iloc[-1] / window.iloc[0])
            all_rets.extend(window.pct_change().dropna().tolist())

        n_days = len(all_rets)
        if n_days >= 10:
            rdt_records[t] = float(cumret - 1)
            vol_records[t] = float(np.std(all_rets) * np.sqrt(252))  # corrigé √252
        else:
            rdt_records[t] = np.nan
            vol_records[t] = np.nan

    return rdt_records, vol_records


# ── SCORES ────────────────────────────────────────────────────────────────────
def score_color(pct):
    """Retourne (bg, fg, label) selon le percentile du score."""
    if pct >= 0.67:   return '#14532d', '#86efac', 'Score élevé'
    elif pct >= 0.33: return '#713f12', '#fde68a', 'Score moyen'
    else:             return '#7f1d1d', '#fca5a5', 'Score faible'


def sig_stars(p):
    """Étoiles de significativité statistique."""
    if p < 0.01: return '★★★'
    if p < 0.05: return '★★'
    if p < 0.10: return '★'
    return 'ns'


# ── STATISTIQUES ──────────────────────────────────────────────────────────────
def winsorize(s, lo=0.01, hi=0.99):
    """Winsorise une série au 1er–99ème percentile."""
    return s.clip(s.quantile(lo), s.quantile(hi))


def prepare_ols_data(df, score_col, secteur_col, min_obs=8):
    """
    Nettoie et stabilise les données pour la régression OLS :
    - Regroupe les secteurs rares (< min_obs) en 'Autres/Divers'
    - Standardise le score (Z-score) → colonne Score_std
    """
    df_clean = df.copy()

    # Regroupement des secteurs rares
    counts = df_clean[secteur_col].value_counts()
    rare   = counts[counts < min_obs].index
    if len(rare) > 0:
        df_clean[secteur_col] = df_clean[secteur_col].replace(rare, 'Autres/Divers')

    # Standardisation du score
    std_val = df_clean[score_col].std()
    if std_val > 0:
        df_clean['Score_std'] = (
            (df_clean[score_col] - df_clean[score_col].mean()) / std_val
        )
    else:
        df_clean['Score_std'] = 0

    return df_clean


def run_ols(df, dep_var, secteur_col, model_type='simple'):
    """
    Lance une régression OLS avec erreurs robustes HC3.
    Retourne le modèle fitté ou None si échantillon insuffisant.

    model_type : 'simple' | 'interaction' | 'fama_french'
    """
    df_r = df.dropna(subset=[dep_var, 'Score_std', secteur_col]).copy()
    df_r[dep_var] = winsorize(df_r[dep_var])

    n_secteurs = df_r[secteur_col].nunique()
    if len(df_r) < (n_secteurs + 10):
        return None

    if model_type == 'interaction':
        formula = f"{dep_var} ~ Score_std * C({secteur_col})"
    elif model_type == 'fama_french':
        formula = f"{dep_var} ~ Score_std + C({secteur_col}) + LogMarketCap + BookToMarket"
    else:
        formula = f"{dep_var} ~ Score_std + C({secteur_col})"

    try:
        return smf.ols(formula, data=df_r).fit(cov_type='HC3')
    except Exception:
        return None
