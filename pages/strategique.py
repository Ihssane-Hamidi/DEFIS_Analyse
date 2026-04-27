"""
pages/strategique.py — Page Analyse Narrative / Trend (ACT uniquement)
TPI · Analyse Financière (Dash)
"""

import pandas as pd
from dash import html, dcc, dash_table, Input, Output


# ══════════════════════════════════════════════════════════════════════════════
# LAYOUT
# ══════════════════════════════════════════════════════════════════════════════
def layout(ctx: dict):
    is_mq = ctx['is_mq']

    if is_mq:
        return html.Div([
            html.Div(className='note-box', style={'marginTop': '20px'}, children=[
                "📊 Cette section (Narrative & Trend) est spécifique au panel ",
                html.Strong("ACT"),
                ". Le panel Management Quality ne contient pas ces indicateurs qualitatifs. "
                "Basculez sur ACT dans le sélecteur de référentiel.",
            ]),
        ])

    return html.Div([
        html.H2(
            'Analyse Stratégique · Narrative & Trend (ACT)',
            style={'fontSize': '16px', 'fontWeight': '500',
                   'color': '#e6edf3', 'marginBottom': '8px'},
        ),
        html.Div(
            className='note-box', style={'marginBottom': '16px'},
            children=[
                "Analyse combinée des performances par profil qualitatif ",
                html.Strong("(Narrative A→E)"),
                " et dynamique ",
                html.Strong("(Trend +/=/−)"),
                ".",
            ],
        ),

        # ── Sélecteur axe ─────────────────────────────────────────────────────
        html.Div(style={'maxWidth': '320px', 'marginBottom': '16px'}, children=[
            html.Div("Axe d'analyse", className='kpi-label'),
            dcc.Dropdown(
                id='strat-view',
                options=[
                    {'label': 'Par Catégorie Narrative (A → E)', 'value': 'narrative'},
                    {'label': 'Par Tendance Trend (+/=/−)',       'value': 'trend'},
                ],
                value='narrative',
                clearable=False,
                style=_dd_style(),
            ),
        ]),

        # ── Résultats dynamiques ──────────────────────────────────────────────
        dcc.Loading(
            type='circle', color='#1f6feb',
            children=html.Div(id='strat-results'),
        ),
    ])


# ══════════════════════════════════════════════════════════════════════════════
# CALLBACKS
# ══════════════════════════════════════════════════════════════════════════════
def register_callbacks(app, data: dict):

    @app.callback(
        Output('strat-results', 'children'),
        Input('strat-view',     'value'),
        Input('store-dataset',  'data'),
    )
    def update_strategique(view_mode, dataset):
        is_mq = (dataset != 'act')

        if is_mq:
            return html.Div(
                "Basculez sur ACT pour accéder à cette analyse.",
                className='warn-box',
            )

        valid        = data['valid_act']
        prices       = data['prices_act']
        brent        = data['brent']
        rallies      = data['rallies']
        narrative_col= data['col_narr_act']
        trend_col    = data['col_trend_act']

        # Config selon axe choisi
        if view_mode == 'narrative':
            target_col  = narrative_col
            categories  = sorted([str(x) for x in valid[target_col].dropna().unique()])
            colors_map  = {
                'A': '#2ecc71', 'B': '#3498db', 'C': '#f1c40f',
                'D': '#e67e22', 'E': '#e74c3c',
            }
            axis_label  = 'Catégorie Narrative'
        else:
            target_col  = trend_col
            categories  = sorted([str(x) for x in valid[target_col].dropna().unique()])
            colors_map  = {'+': '#27ae60', '=': '#95a5a6', '-': '#c0392b'}
            axis_label  = 'Tendance Trend'

        # ── Graphique cumulatif ───────────────────────────────────────────────
        from charts import plot_cumulatif_categories
        fig = plot_cumulatif_categories(
            valid, prices, brent, rallies,
            target_col, categories, colors_map,
        )

        chart_block = html.Div(className='card', children=[
            html.Div(className='card-header', children=[
                html.Span(
                    f'Rendements cumulés · par {axis_label}',
                    className='card-title',
                ),
                html.Span('2023 – 2025', className='card-tag'),
            ]),
            html.Div(className='card-body', children=[
                dcc.Graph(
                    figure=fig,
                    config={'displayModeBar': True,
                            'modeBarButtonsToRemove': ['lasso2d', 'select2d'],
                            'displaylogo': False},
                ),
            ]),
        ])

        # ── Tableau statistique ───────────────────────────────────────────────
        rows_stats = []
        for cat in categories:
            sub = valid[valid[target_col].astype(str) == cat]
            if sub.empty:
                continue
            rows_stats.append({
                axis_label:  cat,
                'N':         len(sub),
                'Rdt 2023':  f"{sub['Rendement_2023'].mean():.1%}"      if 'Rendement_2023'       in sub else 'N/A',
                'Rdt 2024':  f"{sub['Rendement_2024'].mean():.1%}"      if 'Rendement_2024'       in sub else 'N/A',
                'Rdt 2025 ★':f"{sub['Rendement_2025'].mean():.1%}"      if 'Rendement_2025'       in sub else 'N/A',
                'Rdt Total': f"{sub['Rendement_2023_2025'].mean():.1%}" if 'Rendement_2023_2025'  in sub else 'N/A',
                'Vol':       f"{sub['Volatilite_2023_2025'].mean():.1%}"if 'Volatilite_2023_2025' in sub else 'N/A',
                'Sharpe':    f"{sub['Sharpe_2023_2025'].mean():.2f}"    if 'Sharpe_2023_2025'     in sub else 'N/A',
                'MDD':       f"{sub['MaxDrawdown_2023_2025'].mean():.1%}"if 'MaxDrawdown_2023_2025' in sub else 'N/A',
            })

        table_block = html.Div()
        if rows_stats:
            # Couleurs par catégorie pour la colonne axe
            cat_colors = {
                cat: colors_map.get(cat, '#8b949e')
                for cat in categories
            }
            style_cond = [
                {
                    'if': {'column_id': axis_label},
                    'textAlign':  'left',
                    'fontFamily': 'IBM Plex Sans, sans-serif',
                    'fontWeight': '600',
                },
                *[{
                    'if': {'filter_query': f'{{{axis_label}}} = "{cat}"'},
                    'borderLeft': f'2px solid {color}',
                } for cat, color in cat_colors.items()],
            ]

            table_block = html.Div([
                html.Div(
                    f'Résumé statistique · {axis_label}',
                    className='section-title',
                ),
                html.Div(
                    "★ Rdt 2025 = test prédictif de référence",
                    className='note-box',
                    style={'marginBottom': '10px'},
                ),
                html.Div(className='card', children=[
                    dash_table.DataTable(
                        data=rows_stats,
                        columns=[
                            {'name': c, 'id': c}
                            for c in rows_stats[0].keys()
                        ],
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
                        style_data_conditional=style_cond,
                    ),
                ]),
            ])

        # ── Distribution par catégorie ─────────────────────────────────────────
        dist_rows = []
        for cat in categories:
            sub = valid[valid[target_col].astype(str) == cat]
            dist_rows.append({
                axis_label: cat,
                'N':        len(sub),
                'Part':     f"{len(sub)/len(valid):.1%}",
            })

        dist_block = html.Div([
            html.Div('Distribution du panel', className='section-title'),
            html.Div(className='row-2', children=[
                # Mini tableau distribution
                html.Div(className='card', children=[
                    html.Div(className='card-header', children=[
                        html.Span('Répartition par catégorie', className='card-title'),
                    ]),
                    html.Div(className='card-body', children=[
                        dash_table.DataTable(
                            data=dist_rows,
                            columns=[{'name': c, 'id': c} for c in dist_rows[0].keys()],
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
                            style_data_conditional=[{
                                'if': {'column_id': axis_label},
                                'textAlign':  'left',
                                'fontWeight': '600',
                            }],
                        ),
                    ]),
                ]),
                # Note méthodologique
                html.Div(className='card', children=[
                    html.Div(className='card-header', children=[
                        html.Span('Note méthodologique', className='card-title'),
                    ]),
                    html.Div(className='card-body', children=[
                        html.Ul([
                            html.Li("Narrative A (meilleur) → E : évaluation qualitative de la stratégie de transition"),
                            html.Li("Trend + : amélioration du score dans le temps · = : stable · − : dégradation"),
                            html.Li("Rendements cumulés calculés depuis le 1er janvier 2023"),
                            html.Li("★ Rdt 2025 = seul test prédictif valide (scores publiés début 2025)"),
                        ], style={'paddingLeft': '16px', 'lineHeight': '2.2',
                                  'fontSize': '12px', 'color': '#8b949e'}),
                    ]),
                ]),
            ]),
        ])

        return html.Div([
            chart_block,
            html.Div(style={'marginTop': '14px'}, children=[table_block]),
            html.Div(style={'marginTop': '14px'}, children=[dist_block]),
        ])


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def _dd_style():
    return {
        'backgroundColor': '#161b22',
        'color':           '#e6edf3',
        'border':          '0.5px solid #30363d',
        'borderRadius':    '6px',
        'fontSize':        '12px',
    }
