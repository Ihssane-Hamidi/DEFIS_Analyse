"""
pages/brent.py — Page Analyse Brent
TPI · Analyse Financière (Dash)
"""

import pandas as pd
from dash import html, dcc, dash_table, Input, Output
from charts import (
    plot_scatter_ols,
    plot_coefficients_secteurs,
    plot_quintiles_general_vs_brent,
)
from utils import prepare_ols_data, run_ols, sig_stars
from data import PERIODS_LABELS


# ══════════════════════════════════════════════════════════════════════════════
# LAYOUT
# ══════════════════════════════════════════════════════════════════════════════
def layout(ctx: dict):
    periods_options = [
        {'label': v, 'value': k}
        for k, v in PERIODS_LABELS.items()
    ]
    return html.Div([
        html.H2(
            'Analyse Brent · Impact des hausses pétrolières',
            style={'fontSize': '16px', 'fontWeight': '500',
                   'color': '#e6edf3', 'marginBottom': '16px'},
        ),

        html.Div(className='row-3', style={'marginBottom': '16px'}, children=[
            html.Div([
                html.Div('Période modèle général', className='kpi-label'),
                dcc.Dropdown(
                    id='brent-period',
                    options=periods_options,
                    value='2023_2025',
                    clearable=False,
                    style=_dd_style(),
                ),
            ]),
            html.Div([
                html.Div('Variable dépendante', className='kpi-label'),
                dcc.Dropdown(
                    id='brent-dep',
                    options=[
                        {'label': 'Rendement',  'value': 'Rendement'},
                        {'label': 'Volatilité', 'value': 'Volatilite'},
                    ],
                    value='Rendement',
                    clearable=False,
                    style=_dd_style(),
                ),
            ]),
            html.Div([
                html.Div('Modèle OLS', className='kpi-label'),
                dcc.Dropdown(
                    id='brent-model',
                    options=[
                        {'label': 'Simple (Score + Secteur)',      'value': 'simple'},
                        {'label': 'Interaction (Score × Secteur)', 'value': 'interaction'},
                        {'label': 'Fama-French (+ Taille + B/M)', 'value': 'fama_french'},
                    ],
                    value='simple',
                    clearable=False,
                    style=_dd_style(),
                ),
            ]),
        ]),

        dcc.Loading(
            type='circle', color='#1f6feb',
            children=html.Div(id='brent-results'),
        ),
    ])


# ══════════════════════════════════════════════════════════════════════════════
# CALLBACKS
# ══════════════════════════════════════════════════════════════════════════════
def register_callbacks(app, data: dict):

    @app.callback(
        Output('brent-results', 'children'),
        Input('brent-period',  'value'),
        Input('brent-dep',     'value'),
        Input('brent-model',   'value'),
        Input('store-dataset', 'data'),
    )
    def update_brent(period, dep_choice, model_type, dataset):

        # ── 1. Dataset ────────────────────────────────────────────────────────
        # CORRIGÉ : is_mq/is_act/is_ca définis EN PREMIER
        is_mq  = (dataset == 'mq')
        is_act = (dataset == 'act')
        is_ca  = (dataset == 'ca')

        valid        = data['valid_mq']  if is_mq else (data['valid_act']  if is_act else data['valid_ca'])
        score_col    = 'Score_global_MQ' if is_mq else (data['col_score_act']   if is_act else data['col_score_ca'])
        secteur_col  = 'Macro_Secteur'   if is_mq else (data['col_secteur_act'] if is_act else data['col_secteur_ca'])
        quintile_col = 'Quintile_MQ'     if is_mq else ('Quintile_ACT'          if is_act else data['col_quintile_ca'])
        score_label  = 'Score MQ'        if is_mq else ('Score ACT'             if is_act else 'Score CA')

        # ── 2. Métriques Brent — lues depuis le cache APP_DATA ────────────────
        # CORRIGÉ : plus de calc_metriques_brent() ici, déjà calculé au démarrage
        rallies = data['rallies']

        if rallies is None or len(rallies) == 0:
            return html.Div(
                "⚠️ Données Brent non disponibles ou aucun rally détecté.",
                className='warn-box',
            )

        rdt_b = data['rdt_b_mq']  if is_mq else (data['rdt_b_act']  if is_act else data['rdt_b_ca'])
        vol_b = data['vol_b_mq']  if is_mq else (data['vol_b_act']  if is_act else data['vol_b_ca'])

        # ── 3. Construction valid2 ────────────────────────────────────────────
        valid2 = valid.copy()
        valid2['Rendement_Brent']  = valid2['ticker'].map(rdt_b)
        valid2['Volatilite_Brent'] = valid2['ticker'].map(vol_b)
        valid2 = prepare_ols_data(valid2, score_col, secteur_col)
        valid2 = valid2.dropna(subset=[score_col, secteur_col])

        dep_gen   = f"{dep_choice}_{period}"
        dep_brent = f"{dep_choice}_Brent"

        # ── 4. Vérification colonne période ───────────────────────────────────
        if dep_gen not in valid2.columns:
            return html.Div(
                f"⚠️ Colonne '{dep_gen}' introuvable. "
                f"Disponibles : {[c for c in valid2.columns if dep_choice in c]}",
                className='warn-box',
            )

        # ── 5. Régressions OLS (2 seulement) ─────────────────────────────────
        # CORRIGÉ : on fait 2 OLS avec le model_type choisi
        # les OLS interaction pour le graphique secteurs réutilisent
        # les mêmes résultats si model_type == 'interaction'
        m_gen = run_ols(valid2, dep_gen,   secteur_col, model_type)
        m_br  = run_ols(valid2, dep_brent, secteur_col, model_type)

        # OLS interaction pour le graphique secteurs
        # CORRIGÉ : on ne refait pas 2 OLS si déjà en mode interaction
        if model_type == 'interaction':
            m_gen_int = m_gen
            m_br_int  = m_br
        else:
            m_gen_int = run_ols(valid2, dep_gen,   secteur_col, 'interaction')
            m_br_int  = run_ols(valid2, dep_brent, secteur_col, 'interaction')

        # ── 6. Metric cards ───────────────────────────────────────────────────
        if m_gen is not None and m_br is not None:
            c_gen, p_gen = m_gen.params['Score_std'], m_gen.pvalues['Score_std']
            c_br,  p_br  = m_br.params['Score_std'],  m_br.pvalues['Score_std']
            delta = c_br - c_gen

            metric_cards = html.Div(className='row-4', children=[
                _metric_card('Coef. Général',   f"{c_gen:+.3f} {sig_stars(p_gen)}", p_gen < 0.05),
                _metric_card('Coef. Brent-up',  f"{c_br:+.3f} {sig_stars(p_br)}",  p_br  < 0.05),
                _metric_card('Δ (Brent − Gén)', f"{delta:+.3f}",                    delta > 0),
                _metric_card('R² (Gén / Br)',   f"{m_gen.rsquared_adj:.2f} / {m_br.rsquared_adj:.2f}", True),
            ])

            interp_note = html.Div()
            if abs(delta) > 0.05 and p_br < 0.1:
                sens = "accru" if delta > 0 else "atténué"
                interp_note = html.Div(
                    f"Le score {score_label} semble avoir un impact {sens} lors des chocs pétroliers.",
                    className='note-box', style={'marginTop': '12px'},
                )
        else:
            n_brent = valid2['Rendement_Brent'].notna().sum()
            n_gen   = valid2[dep_gen].notna().sum() if dep_gen in valid2.columns else 0
            metric_cards = html.Div(
                f"⚠️ Données insuffisantes pour la régression OLS. "
                f"Lignes valides — Général : {n_gen}, Brent-up : {n_brent}.",
                className='warn-box',
            )
            interp_note = html.Div()

        # ── 7. Scatter Brent-up ───────────────────────────────────────────────
        df_scatter = valid2.dropna(subset=[dep_brent, 'Score_std', quintile_col])
        scatter = html.Div(className='card', children=[
            html.Div(className='card-header', children=[
                html.Span(
                    f'Score standardisé vs {dep_choice} (période Brent-up)',
                    className='card-title',
                ),
            ]),
            html.Div(className='card-body', children=[
                dcc.Graph(
                    figure=plot_scatter_ols(
                        df_scatter, dep_brent, quintile_col,
                        y_label=f'{dep_choice} (Brent-up)',
                    ),
                    config={'displayModeBar': False},
                ),
            ]),
        ]) if not df_scatter.empty else html.Div(
            "Échantillon trop restreint pour le nuage de points.",
            className='warn-box',
        )

        # ── 8. Coefficients par secteur ───────────────────────────────────────
        if m_gen_int and m_br_int:
            data_sect = []
            for s in sorted(valid2[secteur_col].unique()):
                p_g   = m_gen_int.params.get('Score_std', 0)
                key_g = f'Score_std:C({secteur_col})[T.{s}]'
                if key_g in m_gen_int.params:
                    p_g += m_gen_int.params[key_g]

                p_b   = m_br_int.params.get('Score_std', 0)
                key_b = f'Score_std:C({secteur_col})[T.{s}]'
                if key_b in m_br_int.params:
                    p_b += m_br_int.params[key_b]

                data_sect.append({'Secteur': s, 'Modèle': 'Général',  'Coefficient': p_g})
                data_sect.append({'Secteur': s, 'Modèle': 'Brent-up', 'Coefficient': p_b})

            coef_secteurs = html.Div(className='card', children=[
                html.Div(className='card-header', children=[
                    html.Span(
                        'Coefficients par secteur — Général vs Brent-up',
                        className='card-title',
                    ),
                ]),
                html.Div(className='card-body', children=[
                    dcc.Graph(
                        figure=plot_coefficients_secteurs(data_sect),
                        config={'displayModeBar': False},
                    ),
                ]),
            ])
        else:
            coef_secteurs = html.Div(
                "Graphique secteurs non disponible (échantillon trop faible).",
                className='warn-box',
            )

        # ── 9. Quintiles Général vs Brent-up ──────────────────────────────────
        q_data = []
        for q in sorted(valid2[quintile_col].dropna().unique()):
            sub = valid2[valid2[quintile_col] == q]
            q_data.append({'Quintile': q, 'Type': 'Général',  'Valeur': sub[dep_gen].mean()})
            q_data.append({'Quintile': q, 'Type': 'Brent-up', 'Valeur': sub[dep_brent].mean()})

        if q_data:
            df_q     = pd.DataFrame(q_data)
            df_pivot = df_q.pivot(index='Quintile', columns='Type', values='Valeur').reset_index()
            if 'Général' in df_pivot.columns and 'Brent-up' in df_pivot.columns:
                df_pivot['Différence'] = df_pivot['Brent-up'] - df_pivot['Général']
                for col in ['Général', 'Brent-up', 'Différence']:
                    df_pivot[col] = df_pivot[col].apply(lambda x: f"{x:.2%}")

            quintile_section = html.Div([
                html.Div(
                    'Performance moyenne par quintile — Général vs Brent-up',
                    className='section-title',
                ),
                html.Div(className='card', children=[
                    html.Div(className='card-body', children=[
                        dcc.Graph(
                            figure=plot_quintiles_general_vs_brent(df_q),
                            config={'displayModeBar': False},
                        ),
                    ]),
                ]),
                html.Div(className='card', style={'marginTop': '10px'}, children=[
                    dash_table.DataTable(
                        data=df_pivot.to_dict('records'),
                        columns=[{'name': c, 'id': c} for c in df_pivot.columns],
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
                            'if': {'column_id': 'Quintile'},
                            'textAlign': 'left',
                        }],
                    ),
                ]),
            ])
        else:
            quintile_section = html.Div()

        # ── 10. Summaries OLS ─────────────────────────────────────────────────
        summaries = html.Details([
            html.Summary(
                'Consulter les rapports statistiques complets (OLS Summary)',
                style={'cursor': 'pointer', 'color': '#58a6ff',
                       'fontSize': '12px', 'padding': '10px 0'},
            ),
            html.Div(className='row-2', style={'marginTop': '10px'}, children=[
                html.Div([
                    html.Div('Modèle Général', className='section-title'),
                    html.Pre(
                        m_gen.summary().as_text() if m_gen else 'Non disponible',
                        style={'fontSize': '10px', 'color': '#8b949e',
                               'overflowX': 'auto', 'whiteSpace': 'pre'},
                    ),
                ]),
                html.Div([
                    html.Div('Modèle Brent-up', className='section-title'),
                    html.Pre(
                        m_br.summary().as_text() if m_br else 'Non disponible',
                        style={'fontSize': '10px', 'color': '#8b949e',
                               'overflowX': 'auto', 'whiteSpace': 'pre'},
                    ),
                ]),
            ]),
        ])

        # ── 11. Assemblage final ──────────────────────────────────────────────
        return html.Div([
            metric_cards,
            interp_note,
            html.Div(style={'marginTop': '16px'}, children=[scatter]),
            html.Div(style={'marginTop': '14px'}, children=[coef_secteurs]),
            quintile_section,
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


def _dd_style():
    return {
        'backgroundColor': '#161b22',
        'color':           '#e6edf3',
        'border':          '0.5px solid #30363d',
        'borderRadius':    '6px',
        'fontSize':        '12px',
    }
