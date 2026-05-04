"""
pages/composite.py — Page Score Composite Propriétaire (ACT uniquement)
TPI · Analyse Financière (Dash)
"""

import pandas as pd
from dash import html, dcc, dash_table, Input, Output, State
from utils import calc_metriques_brent, prepare_ols_data, sig_stars
from data import PERIODS_LABELS
import statsmodels.formula.api as smf


# ══════════════════════════════════════════════════════════════════════════════
# LAYOUT
# ══════════════════════════════════════════════════════════════════════════════
def layout(ctx: dict):
    is_mq = ctx['is_mq']

    if is_mq:
        return html.Div([
            html.Div(className='note-box', style={'marginTop': '20px'}, children=[
                "💡 Cette analyse est optimisée pour le référentiel ",
                html.Strong("ACT"),
                ". Veuillez basculer sur ACT dans le sélecteur de référentiel.",
            ]),
        ])

    return html.Div([
        html.H2(
            'Simulateur de Score Composite Propriétaire',
            style={'fontSize': '16px', 'fontWeight': '500',
                   'color': '#e6edf3', 'marginBottom': '8px'},
        ),
        html.Div(
            className='note-box', style={'marginBottom': '20px'},
            children=[
                "Construisez votre propre score composite en pondérant les trois dimensions ACT : "
                "Performance (I), Narrative (J) et Trend (K). "
                "Le modèle calcule ensuite l'alpha et la résilience au choc pétrolier.",
            ],
        ),

        # ── Pondération ───────────────────────────────────────────────────────
        html.Div('1. Pondération des variables', className='section-title'),
        html.Div(className='row-3', style={'marginBottom': '8px'}, children=[
            html.Div([
                html.Div('Poids Performance (I)', className='kpi-label'),
                dcc.Input(
                    id='w-perf', type='number',
                    value=100, step=10, min=0, max=500,
                    style=_input_style(),
                ),
            ]),
            html.Div([
                html.Div('Poids Narrative (J)', className='kpi-label'),
                dcc.Input(
                    id='w-narr', type='number',
                    value=100, step=10, min=0, max=500,
                    style=_input_style(),
                ),
            ]),
            html.Div([
                html.Div('Poids Trend (K)', className='kpi-label'),
                dcc.Input(
                    id='w-trend', type='number',
                    value=100, step=10, min=0, max=500,
                    style=_input_style(),
                ),
            ]),
        ]),
        html.Div(
            id='poids-total',
            style={'fontSize': '11px', 'color': '#6e7681', 'marginBottom': '16px'},
        ),

        # ── Bouton calcul ─────────────────────────────────────────────────────
        html.Button(
            'Calculer le score composite',
            id='btn-composite',
            n_clicks=0,
            style={
                'background':    '#1f6feb',
                'color':         '#fff',
                'border':        'none',
                'borderRadius':  '6px',
                'padding':       '9px 20px',
                'fontSize':      '12px',
                'fontWeight':    '500',
                'cursor':        'pointer',
                'marginBottom':  '20px',
                'fontFamily':    'IBM Plex Sans, sans-serif',
            },
        ),

        # ── Résultats ─────────────────────────────────────────────────────────
        dcc.Loading(
            type='circle', color='#1f6feb',
            children=html.Div(id='composite-results'),
        ),
    ])


# ══════════════════════════════════════════════════════════════════════════════
# CALLBACKS
# ══════════════════════════════════════════════════════════════════════════════
def register_callbacks(app, data: dict):

    @app.callback(
        Output('poids-total', 'children'),
        Input('w-perf',  'value'),
        Input('w-narr',  'value'),
        Input('w-trend', 'value'),
    )
    def update_poids_total(w_i, w_j, w_k):
        w_i = w_i or 0
        w_j = w_j or 0
        w_k = w_k or 0
        total = w_i + w_j + w_k
        if total == 0:
            return "⚠ Total des poids = 0, veuillez saisir au moins une valeur."
        return (
            f"Total des poids : {total} · "
            f"Performance : {w_i/total:.0%} · "
            f"Narrative : {w_j/total:.0%} · "
            f"Trend : {w_k/total:.0%}"
        )

    @app.callback(
        Output('composite-results', 'children'),
        Input('btn-composite',  'n_clicks'),
        State('w-perf',  'value'),
        State('w-narr',  'value'),
        State('w-trend', 'value'),
        State('store-dataset', 'data'),
        prevent_initial_call=True,
    )
    def compute_composite(n_clicks, w_i, w_j, w_k, dataset):
        is_mq = (dataset != 'act')
        if is_mq:
            return html.Div(
                "Basculez sur ACT pour utiliser cette fonctionnalité.",
                className='warn-box',
            )

        valid        = data['valid_act'].copy()
        prices       = data['prices_act']
        rallies      = data['rallies']
        col_perf     = data['col_score_act']
        col_narr     = data['col_narr_act']
        col_trend    = data['col_trend_act']
        col_sect     = data['col_secteur_act']

        w_i = w_i or 0
        w_j = w_j or 0
        w_k = w_k or 0
        total_w = w_i + w_j + w_k

        if total_w == 0:
            return html.Div(
                "Total des poids = 0. Veuillez saisir au moins une valeur.",
                className='warn-box',
            )

        # ── Calcul score composite ────────────────────────────────────────────
        map_j = {'A': 100, 'B': 75, 'C': 50, 'D': 25, 'E': 0}
        map_k = {'+': 100, '=': 50, '-': 0}

        valid['val_j'] = valid[col_narr].map(map_j).fillna(50)
        valid['val_k'] = valid[col_trend].map(map_k).fillna(50)
        valid['Composite_Score'] = (
            valid[col_perf] * w_i +
            valid['val_j']  * w_j +
            valid['val_k']  * w_k
        ) / total_w

        # Standardisation Z-score
        std_val = valid['Composite_Score'].std()
        if std_val > 0:
            valid['Score_std'] = (
                (valid['Composite_Score'] - valid['Composite_Score'].mean()) / std_val
            )
        else:
            valid['Score_std'] = 0

        # ── Calcul métriques Brent ────────────────────────────────────────────
        tickers = valid['ticker'].dropna().tolist()
        rdt_b, vol_b = calc_metriques_brent(prices, tickers, rallies)
        valid['Rdt_Brent'] = valid['ticker'].map(rdt_b)

        # ── Régressions ───────────────────────────────────────────────────────
        valid2 = prepare_ols_data(valid, 'Composite_Score', col_sect)

        data_glob  = valid2.dropna(subset=['Rendement_2023_2025', 'Score_std', col_sect])
        data_brent = valid2.dropna(subset=['Rdt_Brent',           'Score_std', col_sect])

        if len(data_glob) < 10 or len(data_brent) < 10:
            return html.Div(
                "Échantillon trop faible pour générer les régressions.",
                className='warn-box',
            )

        try:
            m_glob  = smf.ols(
                f"Rendement_2023_2025 ~ Score_std + C({col_sect})",
                data=data_glob,
            ).fit()
            m_brent = smf.ols(
                f"Rdt_Brent ~ Score_std + C({col_sect})",
                data=data_brent,
            ).fit()
        except Exception as e:
            return html.Div(f"Erreur lors du calcul : {e}", className='warn-box')

        alpha_g  = m_glob.params['Score_std']
        alpha_b  = m_brent.params['Score_std']
        sig_g    = m_glob.pvalues['Score_std']
        sig_b    = m_brent.pvalues['Score_std']
        diff     = alpha_b - alpha_g

        # ── Metric cards ──────────────────────────────────────────────────────
        metric_cards = html.Div(className='row-3', children=[
            _metric_card('Alpha Global (std)',  f'{alpha_g:+.4f} {sig_stars(sig_g)}', sig_g < 0.05),
            _metric_card('Alpha Brent (std)',   f'{alpha_b:+.4f} {sig_stars(sig_b)}', sig_b < 0.05),
            _metric_card('Gain de Résilience',  f'{diff:+.4f}', diff > 0),
        ])

        # Interprétation
        if diff > 0 and sig_b < 0.1:
            interp = html.Div(
                f"✓ Le score composite améliore la résilience lors des chocs pétroliers "
                f"(Δ = {diff:+.4f}).",
                className='note-box',
                style={'marginTop': '10px', 'borderColor': '#3fb950',
                       'background': '#052e16', 'color': '#3fb950'},
            )
        elif diff < 0:
            interp = html.Div(
                f"Le score composite est moins efficace lors des chocs pétroliers "
                f"(Δ = {diff:+.4f}). Essayez d'augmenter le poids Trend.",
                className='warn-box', style={'marginTop': '10px'},
            )
        else:
            interp = html.Div()

        # ── Top 15 entreprises ────────────────────────────────────────────────
        top_df = (
            valid.sort_values('Composite_Score', ascending=False)
            .head(15)[['Company Name', 'ticker', col_perf,
                        col_narr, col_trend, 'Composite_Score']]
            .copy()
        )
        top_df.columns = ['Entreprise', 'Ticker', 'Perf (I)',
                          'Narrative (J)', 'Trend (K)', 'Score Composite']
        top_df['Score Composite'] = top_df['Score Composite'].apply(lambda x: f"{x:.1f}")
        top_df['Perf (I)']        = top_df['Perf (I)'].apply(
            lambda x: f"{x:.1f}" if pd.notna(x) else 'N/A'
        )

        top_table = html.Div([
            html.Div('3. Top 15 · Meilleurs scores composites', className='section-title'),
            html.Div(className='card', children=[
                dash_table.DataTable(
                    data=top_df.to_dict('records'),
                    columns=[{'name': c, 'id': c} for c in top_df.columns],
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
                            'if': {'column_id': 'Entreprise'},
                            'textAlign':  'left',
                            'fontFamily': 'IBM Plex Sans, sans-serif',
                            'color':      '#e6edf3',
                        },
                        {
                            'if': {'column_id': 'Ticker'},
                            'textAlign': 'left',
                            'color':     '#58a6ff',
                        },
                        {
                            'if':   {'column_id': 'Narrative (J)',
                                     'filter_query': '{Narrative (J)} = "A"'},
                            'color': '#3fb950',
                        },
                        {
                            'if':   {'column_id': 'Narrative (J)',
                                     'filter_query': '{Narrative (J)} = "E"'},
                            'color': '#f85149',
                        },
                        {
                            'if':   {'column_id': 'Trend (K)',
                                     'filter_query': '{Trend (K)} = "+"'},
                            'color': '#3fb950',
                        },
                        {
                            'if':   {'column_id': 'Trend (K)',
                                     'filter_query': '{Trend (K)} = "-"'},
                            'color': '#f85149',
                        },
                    ],
                ),
            ]),
        ])

        # ── Summaries OLS ─────────────────────────────────────────────────────
        summaries = html.Details([
            html.Summary(
                'Consulter les rapports statistiques détaillés',
                style={'cursor': 'pointer', 'color': '#58a6ff',
                       'fontSize': '12px', 'padding': '10px 0'},
            ),
            html.Div(className='row-2', style={'marginTop': '10px'}, children=[
                html.Div([
                    html.Div('Régression Période Totale', className='section-title'),
                    html.Pre(
                        m_glob.summary().as_text(),
                        style={'fontSize': '10px', 'color': '#8b949e',
                               'overflowX': 'auto', 'whiteSpace': 'pre'},
                    ),
                ]),
                html.Div([
                    html.Div('Régression Période Brent-Up', className='section-title'),
                    html.Pre(
                        m_brent.summary().as_text(),
                        style={'fontSize': '10px', 'color': '#8b949e',
                               'overflowX': 'auto', 'whiteSpace': 'pre'},
                    ),
                ]),
            ]),
        ])

        return html.Div([
            html.Div('2. Alpha & Résilience au choc pétrolier', className='section-title'),
            metric_cards,
            interp,
            html.Div(style={'marginTop': '16px'}, children=[top_table]),
            html.Div(style={'marginTop': '14px'}, children=[summaries]),
        ])


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def _metric_card(label, value, ok=True):
    color = '#3fb950' if ok else '#f85149'
    return html.Div(className='metric-card', children=[
        html.Div(label, className='metric-label'),
        html.Div(value, className='metric-value', style={'color': color}),
    ])


def _input_style():
    return {
        'width':           '100%',
        'backgroundColor': '#161b22',
        'color':           '#e6edf3',
        'border':          '0.5px solid #30363d',
        'borderRadius':    '6px',
        'padding':         '8px 12px',
        'fontSize':        '13px',
        'fontFamily':      'IBM Plex Mono, monospace',
        'outline':         'none',
    }
