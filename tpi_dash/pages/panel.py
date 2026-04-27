"""
pages/panel.py — Page Panel Quintiles
TPI · Analyse Financière (Dash)
"""

import pandas as pd
from dash import html, dcc, dash_table
from charts import plot_panel_quintiles
from data import PERIODS_LABELS


# ══════════════════════════════════════════════════════════════════════════════
# LAYOUT
# ══════════════════════════════════════════════════════════════════════════════
def layout(ctx: dict):
    is_mq       = ctx['is_mq']
    valid       = ctx['valid']
    prices      = ctx['prices']
    brent       = ctx['brent']
    rallies     = ctx['rallies']
    quintile_col= ctx['quintile_col']
    score_col   = ctx['score_col']

    # ── Graphique cumulatif ───────────────────────────────────────────────────
    fig_panel = plot_panel_quintiles(valid, prices, brent, rallies, quintile_col)

    # ── Tableau résumé ────────────────────────────────────────────────────────
    rows_t = []
    for q in ['Q1', 'Q2', 'Q3', 'Q4', 'Q5']:
        sub = valid[valid[quintile_col] == q]
        if sub.empty:
            continue
        score_fmt = (
            f"{sub[score_col].mean():.1%}"
            if is_mq else f"{sub[score_col].mean():.1f}"
        )
        rows_t.append({
            'Quintile':    q,
            'N':           len(sub),
            'Score moyen': score_fmt,
            'Rdt 2023':    f"{sub['Rendement_2023'].mean():.1%}"       if 'Rendement_2023'       in sub else 'N/A',
            'Rdt 2024':    f"{sub['Rendement_2024'].mean():.1%}"       if 'Rendement_2024'       in sub else 'N/A',
            'Rdt 2025 ★':  f"{sub['Rendement_2025'].mean():.1%}"       if 'Rendement_2025'       in sub else 'N/A',
            'Rdt 23–25':   f"{sub['Rendement_2023_2025'].mean():.1%}"  if 'Rendement_2023_2025'  in sub else 'N/A',
            'Vol':         f"{sub['Volatilite_2023_2025'].mean():.1%}" if 'Volatilite_2023_2025' in sub else 'N/A',
            'Sharpe':      f"{sub['Sharpe_2023_2025'].mean():.2f}"     if 'Sharpe_2023_2025'     in sub else 'N/A',
            'MDD':         f"{sub['MaxDrawdown_2023_2025'].mean():.1%}" if 'MaxDrawdown_2023_2025' in sub else 'N/A',
        })

    quintile_colors = {
        'Q5': '#3fb950', 'Q4': '#56d364',
        'Q3': '#8b949e', 'Q2': '#d29922', 'Q1': '#f85149',
    }

    table = dash_table.DataTable(
        data=rows_t,
        columns=[{'name': c, 'id': c} for c in rows_t[0].keys()] if rows_t else [],
        style_table={'overflowX': 'auto'},
        style_cell={
            'backgroundColor': '#0d1117',
            'color':           '#c9d1d9',
            'fontSize':        '12px',
            'fontFamily':      'IBM Plex Mono, monospace',
            'border':          '0.5px solid #21262d',
            'padding':         '8px 14px',
            'textAlign':       'right',
        },
        style_header={
            'backgroundColor': '#161b22',
            'color':           '#6e7681',
            'fontSize':        '10px',
            'fontWeight':      '400',
            'textTransform':   'uppercase',
            'letterSpacing':   '0.07em',
            'border':          '0.5px solid #21262d',
            'textAlign':       'left',
        },
        style_data_conditional=[
            {
                'if': {'column_id': 'Quintile'},
                'textAlign':  'left',
                'fontFamily': 'IBM Plex Sans, sans-serif',
                'fontWeight': '500',
            },
            *[{
                'if': {'filter_query': f'{{Quintile}} = {q}'},
                'borderLeft': f'2px solid {color}',
            } for q, color in quintile_colors.items()],
        ],
    )

    # ── Assemblage ────────────────────────────────────────────────────────────
    return html.Div([
        html.H2(
            'Panel · Rendements cumulés par quintile',
            style={'fontSize': '16px', 'fontWeight': '500',
                   'color': '#e6edf3', 'marginBottom': '4px'},
        ),
        html.P(
            'Q1 (scores faibles) → Q5 (scores élevés) · Zones bleues = hausses Brent',
            style={'fontSize': '11px', 'color': '#6e7681', 'marginBottom': '16px'},
        ),

        # Graphique cumulatif
        html.Div(className='card', children=[
            html.Div(className='card-header', children=[
                html.Span('Rendements cumulés par quintile', className='card-title'),
                html.Span('2023 – 2025', className='card-tag'),
            ]),
            html.Div(className='card-body', children=[
                dcc.Graph(
                    figure=fig_panel,
                    config={'displayModeBar': True,
                            'modeBarButtonsToRemove': ['lasso2d', 'select2d'],
                            'displaylogo': False},
                ),
            ]),
        ]),

        # Note temporelle
        html.Div(
            className='note-box',
            style={'marginTop': '12px'},
            children=[
                "★ Rdt 2025 = seul test prédictif valide (scores publiés début 2025). "
                "Les rendements 2023 et 2024 ont une valeur descriptive uniquement."
            ],
        ),

        # Tableau résumé
        html.Div('Résumé statistique par quintile', className='section-title'),
        html.Div(className='card', children=[table]),
    ])
