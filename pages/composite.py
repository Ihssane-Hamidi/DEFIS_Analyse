"""
pages/composite.py — Page Score Composite Propriétaire (ACT uniquement)
TPI · Analyse Financière (Dash)
"""

import pandas as pd
from dash import html, dcc, dash_table, Input, Output, State
from utils import calc_metriques_brent, prepare_ols_data, winsorize, run_ols, sig_stars
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

    periods_options = [
        {'label': v, 'value': k}
        for k, v in PERIODS_LABELS.items()
    ]
    dep_options = [
        {'label': 'Rendement',    'value': 'Rendement'},
        {'label': 'Volatilité',   'value': 'Volatilite'},
        {'label': 'Sharpe',       'value': 'Sharpe'},
        {'label': 'Max Drawdown', 'value': 'MaxDrawdown'},
    ]
    model_options = [
        {'label': 'Modèle 1 · Simple (Score + Secteur)',       'value': 'simple'},
        {'label': 'Modèle 2 · Interaction (Score × Secteur)',  'value': 'interaction'},
        {'label': 'Modèle 3 · Fama-French (+ Taille + B/M)',   'value': 'fama_french'},
    ]

    return html.Div([
        html.H2(
            'Simulateur de Score Composite Propriétaire',
            style={'fontSize': '16px', 'fontWeight': '500',
                   'color': '#e6edf3', 'marginBottom': '8px'},
        ),
        html.Div(
            className='note-box', style={'marginBottom': '16px'},
            children=[
                "Construisez votre propre score composite en pondérant les trois dimensions ACT : "
                "Performance (I), Narrative (J) et Trend (K). "
                "Le modèle calcule ensuite l'alpha et la résilience au choc pétrolier.",
            ],
        ),

        # Note temporelle (identique à OLS)
        html.Div(className='note-box', style={'marginBottom': '20px'}, children=[
            "⚠ Note méthodologique : les scores TPI sont issus de l'année fiscale 2023–2024, "
            "publiés en 2025. Les régressions sur Rendement 2023 et 2024 ont une valeur "
            "descriptive uniquement (look-ahead bias). ",
            html.Strong("Le Rendement 2025 constitue le test prédictif de référence."),
        ]),

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

        # ── Sélecteurs régression ─────────────────────────────────────────────
        html.Div('2. Paramètres de la régression', className='section-title'),
        html.Div(className='row-3', style={'marginBottom': '16px'}, children=[
            html.Div([
                html.Div('Période', className='kpi-label'),
                dcc.Dropdown(
                    id='composite-period',
                    options=periods_options,
                    value='2025',
                    clearable=False,
                    style=_dd_style(),
                ),
            ]),
            html.Div([
                html.Div('Variable expliquée', className='kpi-label'),
                dcc.Dropdown(
                    id='composite-dep',
                    options=dep_options,
                    value='Rendement',
                    clearable=False,
                    style=_dd_style(),
                ),
            ]),
            html.Div([
                html.Div('Modèle OLS', className='kpi-label'),
                dcc.Dropdown(
                    id='composite-model',
                    options=model_options,
                    value='simple',
                    clearable=False,
                    style=_dd_style(),
                ),
            ]),
        ]),

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
        Input('btn-composite',     'n_clicks'),
        State('w-perf',            'value'),
        State('w-narr',            'value'),
        State('w-trend',           'value'),
        State('composite-period',  'value'),
        State('composite-dep',     'value'),
        State('composite-model',   'value'),
        State('store-dataset',     'data'),
        prevent_initial_call=True,
    )
    def compute_composite(n_clicks, w_i, w_j, w_k, period, dep_choice, model_type, dataset):
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
        quintile_col = data.get('col_quintile_act', 'Quintile_ACT')
        total_panel  = len(data['valid_act'])

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

        # ── Régression principale (période + variable + modèle choisis) ───────
        dep_var  = f'{dep_choice}_{period}'
        valid2   = prepare_ols_data(valid, 'Composite_Score', col_sect)

        dep_labels = {
            'Rendement': 'Rendement', 'Volatilite': 'Volatilité',
            'Sharpe': 'Sharpe', 'MaxDrawdown': 'Max Drawdown',
        }

        cols_needed = ['Score_std', col_sect, dep_var, 'LogMarketCap', 'BookToMarket']
        df_reg = valid2[[c for c in cols_needed if c in valid2.columns]].dropna().copy()
        df_reg[dep_var] = winsorize(df_reg[dep_var])

        n_reg      = len(df_reg)
        n_secteurs = df_reg[col_sect].nunique()

        if n_reg < (n_secteurs + 15):
            return html.Div(
                f"Données insuffisantes pour {PERIODS_LABELS.get(period, period)} "
                f"({n_reg} observations, {n_secteurs} secteurs). "
                "Choisissez une période plus longue.",
                className='warn-box',
            )

        model = run_ols(df_reg, dep_var, col_sect, model_type)
        if model is None:
            return html.Div(
                "Le calcul a échoué (instabilité numérique). Essayez le Modèle Simple.",
                className='warn-box',
            )

        coef_main = model.params.get('Score_std', 0)
        pval_main = model.pvalues.get('Score_std', 1)

        # ── Régression Brent (toujours modèle simple comme référence) ─────────
        data_brent = valid2.dropna(subset=['Rdt_Brent', 'Score_std', col_sect])
        m_brent    = None
        alpha_b    = None
        sig_b      = None

        if len(data_brent) >= 10:
            try:
                m_brent = smf.ols(
                    f"Rdt_Brent ~ Score_std + C({col_sect})",
                    data=data_brent,
                ).fit()
                alpha_b = m_brent.params['Score_std']
                sig_b   = m_brent.pvalues['Score_std']
            except Exception:
                pass

        diff = (alpha_b - coef_main) if alpha_b is not None else None

        # ── Badge période ─────────────────────────────────────────────────────
        if period == '2025':
            period_badge = html.Div(
                "✓ Test prédictif valide — le score était publié avant cette période.",
                className='note-box',
                style={'marginTop': '8px', 'borderColor': '#3fb950',
                       'background': '#052e16', 'color': '#3fb950'},
            )
        elif period in ('2023', '2024'):
            period_badge = html.Div(
                "⚠ Valeur descriptive uniquement — look-ahead bias : "
                "le score était publié après cette période.",
                className='warn-box',
                style={'marginTop': '8px'},
            )
        else:
            period_badge = html.Div()

        # ── Metric cards ──────────────────────────────────────────────────────
        cards_children = [
            _metric_card(
                f'Alpha {dep_labels.get(dep_choice, dep_choice)} (std)',
                f'{coef_main:+.4f} {sig_stars(pval_main)}',
                pval_main < 0.05,
            ),
            _metric_card('p-value', f'{pval_main:.3f}', pval_main < 0.05),
            _metric_card('R² ajusté', f'{model.rsquared_adj:.3f}', True),
            _metric_card('Observations', f'{int(model.nobs)} / {total_panel}', True),
        ]
        if alpha_b is not None and dep_choice == 'Rendement':
            cards_children.append(
                _metric_card('Alpha Brent (std)', f'{alpha_b:+.4f} {sig_stars(sig_b)}', sig_b < 0.05)
            )
        if diff is not None and dep_choice == 'Rendement':
            cards_children.append(
                _metric_card('Gain de Résilience', f'{diff:+.4f}', diff > 0)
            )

        metric_cards = html.Div(className='row-3', children=cards_children)

        # Note contexte
        context_note = html.Div(
            className='note-box', style={'marginTop': '12px'},
            children=[
                f"Régression sur {n_reg} entreprises "
                f"({n_reg/total_panel:.0%} du panel initial) · "
                "OLS avec erreurs robustes HC3 · Score standardisé (Z-score) · "
                f"Secteurs regroupés (N < 8) · "
                f"{PERIODS_LABELS.get(period, period)} · "
                f"{dep_labels.get(dep_choice, dep_choice)}.",
            ],
        )

        # Interprétation résilience (uniquement si Rendement sélectionné)
        interp = html.Div()
        if diff is not None and dep_choice == 'Rendement':
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

        # ── Tableau coefficients ───────────────────────────────────────────────
        coef_table = _build_coef_table(model, col_sect)

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
            html.Div('4. Top 15 · Meilleurs scores composites', className='section-title'),
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
        summary_children = [
            html.Div([
                html.Div(
                    f'Régression · {dep_labels.get(dep_choice, dep_choice)} '
                    f'· {PERIODS_LABELS.get(period, period)}',
                    className='section-title',
                ),
                html.Pre(
                    model.summary().as_text(),
                    style={'fontSize': '10px', 'color': '#8b949e',
                           'overflowX': 'auto', 'whiteSpace': 'pre'},
                ),
            ]),
        ]
        if m_brent is not None and dep_choice == 'Rendement':
            summary_children.append(html.Div([
                html.Div('Régression Période Brent-Up', className='section-title'),
                html.Pre(
                    m_brent.summary().as_text(),
                    style={'fontSize': '10px', 'color': '#8b949e',
                           'overflowX': 'auto', 'whiteSpace': 'pre'},
                ),
            ]))

        summaries = html.Details([
            html.Summary(
                'Consulter les rapports statistiques détaillés',
                style={'cursor': 'pointer', 'color': '#58a6ff',
                       'fontSize': '12px', 'padding': '10px 0'},
            ),
            html.Div(className='row-2', style={'marginTop': '10px'},
                     children=summary_children),
        ])

        return html.Div([
            html.Div('3. Alpha & Résultats de régression', className='section-title'),
            metric_cards,
            context_note,
            period_badge,
            interp,
            html.Div(style={'marginTop': '14px'}, children=[coef_table]),
            html.Div(style={'marginTop': '16px'}, children=[top_table]),
            html.Div(style={'marginTop': '14px'}, children=[summaries]),
        ])


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def _build_coef_table(model, secteur_col):
    """Tableau des coefficients du modèle avec p-values et étoiles."""
    rows = []
    for param, coef in model.params.items():
        pval  = model.pvalues.get(param, 1)
        stars = sig_stars(pval)
        label = (param
                 .replace(f'C({secteur_col})[T.', '')
                 .replace(']', '')
                 .replace('Score_std', 'Score (std)')
                 .replace('Intercept', 'Constante')
                 .replace('LogMarketCap', 'Log(MarketCap)')
                 .replace('BookToMarket', 'Book/Market'))
        rows.append({
            'Paramètre': label,
            'Coef.':     f'{coef:+.4f}',
            'p-value':   f'{pval:.3f}',
            'Sig.':      stars,
        })

    return html.Div([
        html.Div('Coefficients du modèle', className='section-title'),
        html.Div(className='card', children=[
            dash_table.DataTable(
                data=rows,
                columns=[{'name': c, 'id': c} for c in rows[0].keys()] if rows else [],
                style_table={'overflowX': 'auto', 'maxHeight': '320px',
                             'overflowY': 'auto'},
                style_cell={
                    'backgroundColor': '#0d1117',
                    'color':           '#c9d1d9',
                    'fontSize':        '12px',
                    'fontFamily':      'IBM Plex Mono, monospace',
                    'border':          '0.5px solid #21262d',
                    'padding':         '6px 14px',
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
                        'if': {'column_id': 'Paramètre'},
                        'textAlign':  'left',
                        'fontFamily': 'IBM Plex Sans, sans-serif',
                        'color':      '#8b949e',
                    },
                    {
                        'if': {'filter_query': '{Sig.} = "★★★"'},
                        'color': '#3fb950',
                    },
                    {
                        'if': {'filter_query': '{Sig.} = "★★"'},
                        'color': '#56d364',
                    },
                    {
                        'if': {'filter_query': '{Sig.} = "★"'},
                        'color': '#d29922',
                    },
                ],
            ),
        ]),
    ])


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


def _dd_style():
    return {
        'backgroundColor': '#161b22',
        'color':           '#e6edf3',
        'border':          '0.5px solid #30363d',
        'borderRadius':    '6px',
        'fontSize':        '12px',
    }
