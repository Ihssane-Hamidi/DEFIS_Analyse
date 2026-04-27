"""
pages/societe.py — Page Société
TPI · Analyse Financière (Dash)
"""

from dash import html, dcc, Input, Output, State, dash_table, callback_context
import dash
from utils import score_color
from charts import plot_rendements_societe, plot_metriques_periode
from data import PERIODS_LABELS


# ══════════════════════════════════════════════════════════════════════════════
# LAYOUT
# ══════════════════════════════════════════════════════════════════════════════
def layout(ctx: dict):
    is_mq       = ctx['is_mq']
    valid       = ctx['valid']
    company_col = 'Company Name'

    companies = sorted(valid[company_col].unique().tolist())
    default   = companies[0] if companies else None

    return html.Div([
        html.Div(className='row-2', style={'alignItems': 'flex-start'}, children=[

            # ── Panneau gauche : sélection + score ───────────────────────────
            html.Div([
                html.Div('Sélection', className='section-title'),
                dcc.Dropdown(
                    id='societe-dropdown',
                    options=[{'label': c, 'value': c} for c in companies],
                    value=default,
                    placeholder='Rechercher une entreprise...',
                    style={
                        'backgroundColor': '#161b22',
                        'color':           '#e6edf3',
                        'border':          '0.5px solid #30363d',
                        'borderRadius':    '6px',
                        'fontSize':        '12px',
                    },
                    className='dash-dropdown-dark',
                ),
                html.Div(id='societe-score-panel', style={'marginTop': '14px'}),
            ], style={'maxWidth': '280px'}),

            # ── Panneau droit : graphiques ────────────────────────────────────
            html.Div([
                html.Div(id='societe-main-content'),
            ], style={'flex': '1', 'minWidth': '0'}),
        ]),
    ])


# ══════════════════════════════════════════════════════════════════════════════
# CALLBACKS
# ══════════════════════════════════════════════════════════════════════════════
def register_callbacks(app, data: dict):

    @app.callback(
        Output('societe-score-panel',  'children'),
        Output('societe-main-content', 'children'),
        Input('societe-dropdown', 'value'),
        Input('store-dataset',    'data'),
    )
    def update_societe(company_name, dataset):
        if not company_name:
            return html.Div(), html.Div()

        is_mq       = (dataset != 'act')
        valid       = data['valid_mq']   if is_mq else data['valid_act']
        prices      = data['prices_mq']  if is_mq else data['prices_act']
        brent       = data['brent']
        rallies     = data['rallies']
        score_col   = 'Score_global_MQ' if is_mq else data['col_score_act']
        quintile_col= 'Quintile_MQ'     if is_mq else 'Quintile_ACT'
        pct_col     = 'MQ_percentile'   if is_mq else 'Score_percentile'
        score_label = 'Score global MQ' if is_mq else 'Performance Score /100'

        row = valid[valid['Company Name'] == company_name]
        if row.empty:
            return html.Div("Entreprise non trouvée."), html.Div()
        row = row.iloc[0]

        ticker = row['ticker']

        # ── Score panel ───────────────────────────────────────────────────────
        bg, fg, label = score_color(float(row[pct_col]))
        score_val     = row[score_col]
        score_fmt     = (
            f"{score_val:.1%}"
            if score_val <= 1 else f"{score_val:.1f}/100"
        )

        if is_mq:
            extra_items = [
                ('Niveau',       row.get('Level',         'N/A')),
                ('Quintile',     row.get('Quintile_MQ',   'N/A')),
                ('Secteur',      row.get('Sector',        'N/A')),
                ('Macro-secteur',row.get('Macro_Secteur', 'N/A')),
                ('Géographie',   row.get('Geography',     'N/A')),
            ]
        else:
            col_J = data['col_narr_act']
            col_K = data['col_trend_act']
            col_s = data['col_secteur_act']
            extra_items = [
                ('Narrative', row.get(col_J, 'N/A')),
                ('Trend',     row.get(col_K, 'N/A')),
                ('Secteur',   row.get(col_s, 'N/A')),
                ('Quintile',  row.get('Quintile_ACT', 'N/A')),
            ]

        score_panel = html.Div(className='metric-card', children=[
            html.Div(score_label, className='metric-label'),
            html.Div(score_fmt,   className='metric-value', style={'color': fg}),
            html.Div(style={'marginTop': '10px'}, children=[
                html.Span(
                    f"{label} · {row[pct_col]:.0%} du panel",
                    className='score-badge',
                    style={'background': bg, 'color': fg},
                ),
            ]),
            html.Div(style={'marginTop': '12px', 'fontSize': '12px',
                            'color': '#6e7681', 'lineHeight': '1.9'},
                     children=[
                         html.Div([
                             html.Span(f"{k} : ", style={'color': '#8b949e'}),
                             html.Span(str(v)),
                         ])
                         for k, v in extra_items
                     ]),
        ])

        # ── Graphiques ────────────────────────────────────────────────────────
        if ticker not in prices.columns:
            main = html.Div(
                f"Prix non disponibles pour {ticker}",
                className='warn-box',
            )
            return score_panel, main

        px_series = prices[ticker].dropna()
        if len(px_series) < 50:
            main = html.Div(
                f"Données insuffisantes pour {ticker} ({len(px_series)} jours)",
                className='warn-box',
            )
            return score_panel, main

        periods = list(PERIODS_LABELS.keys())
        labels  = list(PERIODS_LABELS.values())

        main = html.Div([
            html.H3(
                f"{company_name}  ·  {ticker}",
                style={'fontSize': '15px', 'fontWeight': '500',
                       'color': '#e6edf3', 'marginBottom': '12px'},
            ),

            # Rendements journaliers
            html.Div('Rendements journaliers · Zones bleues = hausses Brent',
                     className='section-title'),
            html.Div(className='card', children=[
                html.Div(className='card-body', children=[
                    dcc.Graph(
                        figure=plot_rendements_societe(
                            px_series, ticker, brent, rallies, company_name
                        ),
                        config={'displayModeBar': False},
                    ),
                ]),
            ]),

            # Performance par période
            html.Div('Performance par période', className='section-title'),
            html.Div(className='card', children=[
                html.Div(className='card-body', children=[
                    dcc.Graph(
                        figure=plot_metriques_periode(row, periods, labels),
                        config={'displayModeBar': False},
                    ),
                ]),
            ]),

            # Métriques détaillées
            html.Div('Métriques financières', className='section-title'),
            _metriques_table(row, periods, labels),
        ])

        return score_panel, main


def _metriques_table(row, periods, labels):
    """Tableau des métriques par période."""
    cols_map = {
        'Rendement':    'Rendement',
        'Volatilite':   'Volatilité',
        'Sharpe':       'Sharpe',
        'MaxDrawdown':  'Max Drawdown',
    }
    rows = []
    for metric, metric_label in cols_map.items():
        r = {'Métrique': metric_label}
        for p, lbl in zip(periods, labels):
            val = row.get(f'{metric}_{p}', None)
            if val is None:
                r[lbl] = 'N/A'
            elif metric in ('Rendement', 'Volatilite', 'MaxDrawdown'):
                r[lbl] = f"{val:.1%}"
            else:
                r[lbl] = f"{val:.2f}"
        rows.append(r)

    columns = [{'name': 'Métrique', 'id': 'Métrique'}] + [
        {'name': lbl, 'id': lbl} for lbl in labels
    ]

    return html.Div(className='card', children=[
        dash_table.DataTable(
            data=rows,
            columns=columns,
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
                'if': {'column_id': 'Métrique'},
                'textAlign':  'left',
                'fontFamily': 'IBM Plex Sans, sans-serif',
                'color':      '#8b949e',
            }],
        ),
    ])
