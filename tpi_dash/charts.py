#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Apr 27 00:54:00 2026

@author: hamidi
"""

"""
charts.py — Fonctions graphiques Plotly
TPI · Analyse Financière (Dash)
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

from data import PLOTLY_LAYOUT, QUINTILE_COLORS, PERIODS_LABELS
from utils import add_oil_rectangles


# ── SOCIÉTÉ ───────────────────────────────────────────────────────────────────
def plot_rendements_societe(prices_col, ticker, brent, rallies, company_name):
    """
    Graphique rendements journaliers (barres) + Brent base 100 (axe secondaire).
    prices_col : pd.Series des prix de la société
    """
    ret_daily  = prices_col.pct_change().dropna()
    brent_al   = brent.reindex(ret_daily.index, method='ffill').dropna()
    brent_norm = brent_al / brent_al.iloc[0] * 100

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig = add_oil_rectangles(fig, rallies, first_only=True)
    fig.add_hline(y=0, line_width=0.5, line_color='rgba(255,255,255,0.15)')

    bar_col = [
        'rgba(239,68,68,0.8)' if v < 0 else 'rgba(52,211,153,0.8)'
        for v in ret_daily.values
    ]
    fig.add_trace(go.Bar(
        x=ret_daily.index, y=ret_daily.values,
        marker_color=bar_col, name='Rendement journalier',
        hovertemplate='%{x|%d %b %Y}<br>%{y:.2%}<extra></extra>',
    ), secondary_y=False)

    fig.add_trace(go.Scatter(
        x=brent_norm.index, y=brent_norm.values,
        name='Brent (base 100)',
        line=dict(color='rgba(59,130,246,0.7)', width=1.5),
        hovertemplate='%{x|%d %b %Y}<br>Brent: %{y:.1f}<extra></extra>',
    ), secondary_y=True)

    fig.update_layout(
        **PLOTLY_LAYOUT, height=340, showlegend=True,
        legend=dict(orientation='h', yanchor='bottom', y=1.02, x=0),
        title=dict(text=f"{company_name} · {ticker}", font=dict(size=13)),
    )
    fig.update_yaxes(
        tickformat='.1%', title_text='Rendement',
        gridcolor='rgba(255,255,255,0.05)', secondary_y=False,
    )
    fig.update_yaxes(
        title_text='Brent (base 100)',
        gridcolor='rgba(0,0,0,0)', secondary_y=True,
    )
    return fig


def plot_metriques_periode(row, periods=None, labels=None):
    """
    Barres Rendement / Volatilité annualisée / Sharpe par période.
    row : pd.Series (ligne d'un DataFrame valid)
    """
    if periods is None:
        periods = list(PERIODS_LABELS.keys())
    if labels is None:
        labels = list(PERIODS_LABELS.values())

    rendements = [row.get(f'Rendement_{p}', np.nan)  for p in periods]
    vols       = [row.get(f'Volatilite_{p}', np.nan) for p in periods]
    sharpes    = [row.get(f'Sharpe_{p}', np.nan)     for p in periods]

    r_col = [
        'rgba(239,68,68,0.8)' if (v and v < 0) else 'rgba(52,211,153,0.8)'
        for v in rendements
    ]
    s_col = [
        'rgba(239,68,68,0.8)' if (v and v < 0) else 'rgba(251,191,36,0.8)'
        for v in sharpes
    ]

    fig = make_subplots(
        rows=1, cols=3, horizontal_spacing=0.08,
        subplot_titles=('Rendement', 'Volatilité annualisée', 'Sharpe'),
    )
    fig.add_trace(go.Bar(
        x=labels, y=rendements, marker_color=r_col,
        hovertemplate='%{x}<br>%{y:.1%}<extra></extra>',
    ), row=1, col=1)
    fig.add_trace(go.Bar(
        x=labels, y=vols, marker_color='rgba(99,179,237,0.7)',
        hovertemplate='%{x}<br>%{y:.1%}<extra></extra>',
    ), row=1, col=2)
    fig.add_trace(go.Bar(
        x=labels, y=sharpes, marker_color=s_col,
        hovertemplate='%{x}<br>%{y:.2f}<extra></extra>',
    ), row=1, col=3)

    fig.update_layout(**PLOTLY_LAYOUT, height=280, showlegend=False)
    fig.update_yaxes(tickformat='.0%', row=1, col=1)
    fig.update_yaxes(tickformat='.0%', row=1, col=2)
    return fig


# ── PANEL QUINTILES ───────────────────────────────────────────────────────────
def plot_panel_quintiles(valid, prices, brent, rallies, quintile_col):
    """
    Courbes de rendement cumulé par quintile + Brent axe secondaire.
    """
    brent_norm = brent / brent.iloc[0] * 100
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig = add_oil_rectangles(fig, rallies, first_only=True)
    fig.add_hline(y=0, line_width=0.5, line_color='rgba(255,255,255,0.15)')

    for q in ['Q1', 'Q2', 'Q3', 'Q4', 'Q5']:
        tickers_q = valid[valid[quintile_col] == q]['ticker'].dropna().tolist()
        tickers_q = [t for t in tickers_q if t in prices.columns]
        if not tickers_q:
            continue
        cum = (1 + prices[tickers_q].pct_change()).cumprod() - 1
        cum_r = cum.mean(axis=1).dropna()
        fig.add_trace(go.Scatter(
            x=cum_r.index, y=cum_r.values,
            name=f'{q} (n={len(tickers_q)})',
            line=dict(color=QUINTILE_COLORS[q], width=2),
            hovertemplate='%{x|%d %b %Y}<br>%{y:.1%}<extra>' + q + '</extra>',
        ), secondary_y=False)

    fig.add_trace(go.Scatter(
        x=brent_norm.index, y=brent_norm.values,
        name='Brent (base 100)',
        line=dict(color='rgba(59,130,246,0.5)', width=1.5, dash='dot'),
    ), secondary_y=True)

    fig.update_layout(
        **PLOTLY_LAYOUT, height=470,
        legend=dict(orientation='h', yanchor='bottom', y=1.02, x=0),
    )
    fig.update_yaxes(
        tickformat='.0%', title_text='Rendement cumulé',
        gridcolor='rgba(255,255,255,0.05)', secondary_y=False,
    )
    fig.update_yaxes(
        title_text='Brent (base 100)',
        gridcolor='rgba(0,0,0,0)', secondary_y=True,
    )
    return fig


# ── OLS ───────────────────────────────────────────────────────────────────────
def plot_scatter_ols(df, dep_var, quintile_col, x_col='Score_std',
                     x_label='Score (standardisé)', y_label=None):
    """Nuage de points Score vs variable dépendante, coloré par quintile."""
    if y_label is None:
        y_label = dep_var

    fig = px.scatter(
        df.dropna(subset=[x_col, dep_var, quintile_col]),
        x=x_col, y=dep_var,
        color=quintile_col,
        trendline='ols',
        color_discrete_map=QUINTILE_COLORS,
        hover_name='ticker',
        labels={x_col: x_label, dep_var: y_label},
    )
    fig.update_layout(**PLOTLY_LAYOUT, height=450)
    return fig


def plot_coefficients_secteurs(data_sect):
    """
    Barres horizontales des coefficients OLS par secteur (Général vs Brent-up).
    data_sect : liste de dicts {Secteur, Modèle, Coefficient}
    """
    import pandas as pd
    df = pd.DataFrame(data_sect)
    fig = px.bar(
        df, x='Coefficient', y='Secteur', color='Modèle',
        barmode='group', orientation='h',
        color_discrete_map={'Général': '#636EFA', 'Brent-up': '#EF553B'},
    )
    fig.update_layout(
        **PLOTLY_LAYOUT, height=600,
        margin=dict(l=20, r=20, t=20, b=20),
    )
    return fig


def plot_quintiles_general_vs_brent(df_q):
    """
    Barres groupées : rendement moyen par quintile — Général vs Brent-up.
    df_q : DataFrame avec colonnes [Quintile, Type, Valeur]
    """
    fig = px.bar(
        df_q, x='Quintile', y='Valeur', color='Type',
        barmode='group',
        color_discrete_map={'Général': '#AB63FA', 'Brent-up': '#FFA15A'},
    )
    fig.update_layout(**PLOTLY_LAYOUT, yaxis_tickformat='.1%', height=400)
    return fig


# ── STRATÉGIQUE ───────────────────────────────────────────────────────────────
def plot_cumulatif_categories(valid, prices, brent, rallies,
                               target_col, categories, colors_map):
    """
    Courbes cumulées par catégorie (Narrative ou Trend) + Brent.
    """
    brent_norm = brent / brent.iloc[0] * 100
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig = add_oil_rectangles(fig, rallies, first_only=True)

    for cat in categories:
        tickers_cat = (
            valid[valid[target_col].astype(str) == cat]['ticker']
            .dropna().tolist()
        )
        tickers_cat = [t for t in tickers_cat if t in prices.columns]
        if not tickers_cat:
            continue
        cum = (1 + prices[tickers_cat].pct_change()).cumprod() - 1
        cum_r = cum.mean(axis=1).dropna()
        fig.add_trace(go.Scatter(
            x=cum_r.index, y=cum_r.values,
            name=f'{cat} (n={len(tickers_cat)})',
            line=dict(color=colors_map.get(cat, '#ffffff'), width=2.5),
            hovertemplate='<b>' + str(cat) + '</b><br>%{y:.1%}<extra></extra>',
        ), secondary_y=False)

    fig.add_trace(go.Scatter(
        x=brent_norm.index, y=brent_norm.values, name='Brent',
        line=dict(color='rgba(59,130,246,0.4)', width=1.5, dash='dot'),
    ), secondary_y=True)

    fig.update_layout(**PLOTLY_LAYOUT, height=500)
    return fig