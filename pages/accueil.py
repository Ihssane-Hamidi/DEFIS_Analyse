"""
pages/accueil.py — Page d'accueil
TPI · Analyse Financière (Dash)
"""

import pandas as pd
from dash import html, dash_table
from data import PERIODS_LABELS


# ══════════════════════════════════════════════════════════════════════════════
# LAYOUT
# ══════════════════════════════════════════════════════════════════════════════
def layout(ctx: dict):
    is_mq  = ctx['is_mq']
    is_act = ctx['is_act']
    is_ca  = ctx['is_ca']
    is_cp  = ctx['is_cp']
    valid  = ctx['valid']
    df_mq  = ctx['df_mq']
    df_act = ctx['df_act']
    df_ca  = ctx['df_ca']
    df_cp  = ctx['df_cp']
    rallies = ctx['rallies']

    # ── Total panel ───────────────────────────────────────────────────────────
    if is_mq:
        total = len(df_mq)
    elif is_act:
        total = len(df_act)
    elif is_ca:
        total = len(df_ca)
    else:
        total = len(df_cp)

    safe_total = max(total, 1)
    avec   = len(valid)
    avec_f = valid['MarketCap'].notna().sum() if 'MarketCap' in valid.columns else 0

    # ── Titre / sous-titre ────────────────────────────────────────────────────
    if is_mq:
        titre = "TPI Management Quality · Analyse Financière"
        sous  = "Édition 2025 · Données boursières 2023–2025"
    elif is_act:
        titre = "ACT — Assessing low Carbon Transition · Analyse Financière"
        sous  = "Évaluation 2025 · Données boursières 2023–2025"
    elif is_ca:
        titre = "CA — Climate Action 100+ · Analyse de Performance"
        sous  = "Édition 2025 · Analyse des Métriques"
    else:  # CP
        titre = "CP — Carbon Performance TPI · Analyse Financière"
        sous  = "Évaluation 2025 · Alignement climatique 2023–2025"

    # ── KPI cards ─────────────────────────────────────────────────────────────
    kpis = [
        {
            'label': 'Entreprises (total)',
            'value': f"{total:,}",
            'sub':   'Panel complet',
            'color': '#58a6ff',
            'accent': 'linear-gradient(90deg,#1d4ed8,#0ea5e9)',
        },
        {
            'label': 'Avec données boursières',
            'value': f"{avec:,}",
            'sub':   f"{avec/safe_total:.0%} du panel",
            'color': '#3fb950',
            'accent': 'linear-gradient(90deg,#059669,#10b981)',
        },
        {
            'label': 'Avec fondamentaux',
            'value': f"{avec_f:,}",
            'sub':   'MarketCap · Book/Market',
            'color': '#a78bfa',
            'accent': 'linear-gradient(90deg,#7c3aed,#a855f7)',
        },
        {
            'label': 'Hausses Brent détectées',
            'value': str(len(rallies)),
            'sub':   'Seuil +15% · fenêtre 60j',
            'color': '#d29922',
            'accent': 'linear-gradient(90deg,#d97706,#f59e0b)',
        },
    ]

    kpi_cards = html.Div(className='kpi-grid', children=[
        html.Div(className='kpi-card', children=[
            html.Div(style={'background': k['accent']}, className='kpi-accent'),
            html.Div(k['label'], className='kpi-label'),
            html.Div(k['value'], className='kpi-value', style={'color': k['color']}),
            html.Div(k['sub'],   className='kpi-sub'),
        ])
        for k in kpis
    ])

    # ── Méthodologie ──────────────────────────────────────────────────────────
    if is_mq:
        methodo_items = [
            "Score MQ : moyenne des réponses Oui/Non aux 23 questions (Q1L0 → Q23L5)",
            f"Quintiles : calculés sur le score global continu, entreprises cotées uniquement ({avec} entreprises)",
            "Régression OLS : winsorisée au 1er–99ème percentile · erreurs robustes HC3",
            f"⚠ Biais de sélection : analyse limitée aux entreprises cotées ({avec/safe_total:.0%} du panel TPI MQ)",
            "⚠ Note temporelle : scores issus de l'année fiscale 2023–2024, publiés en 2025. "
            "Les régressions sur Rendement 2023 et 2024 ont une valeur descriptive uniquement. "
            "Le Rendement 2025 constitue le test prédictif de référence.",
        ]
    elif is_act:
        methodo_items = [
            "Score ACT : Performance Score /100 — évaluation de la trajectoire de décarbonation",
            "Narrative Score : note A (meilleur) à E — évaluation qualitative",
            "Trend Score : tendance +/=/− de la performance dans le temps",
            f"Quintiles : calculés sur le Performance Score, entreprises cotées uniquement ({avec} entreprises)",
            "Régression OLS : winsorisée au 1er–99ème percentile · erreurs robustes HC3",
            f"⚠ Biais de sélection : analyse limitée aux entreprises cotées ({avec/safe_total:.0%} du panel ACT)",
            "⚠ Note temporelle : scores issus de l'année fiscale 2023–2024, publiés en 2025. "
            "Les régressions sur Rendement 2023 et 2024 ont une valeur descriptive uniquement. "
            "Le Rendement 2025 constitue le test prédictif de référence.",
        ]
    elif is_ca:
        methodo_items = [
            "Score CA100 : basé sur les indicateurs Sub-indicator (Yes=1 / Partial=0.5 / No=0)",
            f"Quintiles : calculés sur le Score global CA, entreprises cotées uniquement ({avec} entreprises)",
            "Régression OLS : winsorisée au 1er–99ème percentile · erreurs robustes HC3",
            f"⚠ Biais de sélection : analyse limitée aux entreprises cotées ({avec/safe_total:.0%} du panel CA)",
            "⚠ Note temporelle : scores issus de l'année fiscale 2023–2024, publiés en 2025. "
            "Les régressions sur Rendement 2023 et 2024 ont une valeur descriptive uniquement. "
            "Le Rendement 2025 constitue le test prédictif de référence.",
        ]
    else:  # CP
        methodo_items = [
            "Score CP : moyenne des alignements climatiques (1.5°C Aligned=5 → Not Aligned=1)",
            "Alignement le plus récent : dernière colonne d'alignement non nulle",
            f"Quintiles : calculés sur le Score global CP, entreprises cotées uniquement ({avec} entreprises)",
            "Régression OLS : winsorisée au 1er–99ème percentile · erreurs robustes HC3",
            f"⚠ Biais de sélection : analyse limitée aux entreprises cotées ({avec/safe_total:.0%} du panel CP)",
            "⚠ Note temporelle : scores issus de l'année fiscale 2023–2024, publiés en 2025. "
            "Les régressions sur Rendement 2023 et 2024 ont une valeur descriptive uniquement. "
            "Le Rendement 2025 constitue le test prédictif de référence.",
        ]

    methodo = html.Div([
        html.Div('Méthodologie', className='section-title'),
        html.Div(className='note-box', children=[
            html.Ul([html.Li(item) for item in methodo_items],
                    style={'paddingLeft': '16px', 'lineHeight': '2'})
        ]),
    ])

    # ── Tableau rallies Brent ─────────────────────────────────────────────────
    if rallies:
        rally_df = pd.DataFrame(rallies, columns=['Début', 'Fin'])
        rally_df['Durée (jours)'] = (rally_df['Fin'] - rally_df['Début']).dt.days
        rally_df['Début'] = rally_df['Début'].dt.strftime('%d/%m/%Y')
        rally_df['Fin']   = rally_df['Fin'].dt.strftime('%d/%m/%Y')

        rally_table = html.Div([
            html.Div('Périodes de hausse Brent détectées', className='section-title'),
            html.Div(className='card', children=[
                dash_table.DataTable(
                    data=rally_df.to_dict('records'),
                    columns=[{'name': c, 'id': c} for c in rally_df.columns],
                    style_table={'overflowX': 'auto'},
                    style_cell={
                        'backgroundColor': '#0d1117',
                        'color': '#c9d1d9',
                        'fontSize': '12px',
                        'fontFamily': 'IBM Plex Sans, sans-serif',
                        'border': '0.5px solid #21262d',
                        'padding': '8px 14px',
                    },
                    style_header={
                        'backgroundColor': '#161b22',
                        'color': '#6e7681',
                        'fontSize': '10px',
                        'fontWeight': '400',
                        'textTransform': 'uppercase',
                        'letterSpacing': '0.07em',
                        'border': '0.5px solid #21262d',
                    },
                    style_data_conditional=[{
                        'if': {'row_index': 'odd'},
                        'backgroundColor': '#0d1117',
                    }],
                )
            ]),
        ])
    else:
        rally_table = html.Div(
            html.Div("Aucune hausse Brent détectée sur la période.", className='warn-box')
        )

    # ── Résumé statistique par quintile ──────────────────────────────────────
    valid_q = ctx['valid']
    q_col   = ctx['quintile_col']
    s_col   = ctx['score_col']

    if q_col not in valid_q.columns or valid_q.empty:
        quintile_table = html.Div(
            html.Div("Aucune donnée disponible pour ce dataset.", className='note-box')
        )
    else:
        rows_t = []
        for q in ['Q1', 'Q2', 'Q3', 'Q4', 'Q5']:
            sub = valid_q[valid_q[q_col] == q]
            if sub.empty:
                continue
            score_fmt = (
                f"{sub[s_col].mean():.1f}%"
                if (is_mq or is_act)
                else f"{sub[s_col].mean() * 100:.1f}%"
            )
            rows_t.append({
                'Quintile':    q,
                'N':           len(sub),
                'Score moyen': score_fmt,
                'Rdt 2023':   f"{sub['Rendement_2023'].mean():.1%}"       if 'Rendement_2023'       in sub.columns else 'N/A',
                'Rdt 2024':   f"{sub['Rendement_2024'].mean():.1%}"       if 'Rendement_2024'       in sub.columns else 'N/A',
                'Rdt 2025 ★': f"{sub['Rendement_2025'].mean():.1%}"       if 'Rendement_2025'       in sub.columns else 'N/A',
                'Rdt 23–25':  f"{sub['Rendement_2023_2025'].mean():.1%}"  if 'Rendement_2023_2025'  in sub.columns else 'N/A',
                'Vol':        f"{sub['Volatilite_2023_2025'].mean():.1%}" if 'Volatilite_2023_2025' in sub.columns else 'N/A',
                'Sharpe':     f"{sub['Sharpe_2023_2025'].mean():.2f}"     if 'Sharpe_2023_2025'     in sub.columns else 'N/A',
                'MDD':        f"{sub['MaxDrawdown_2023_2025'].mean():.1%}" if 'MaxDrawdown_2023_2025' in sub.columns else 'N/A',
            })

        if rows_t:
            quintile_table = html.Div([
                html.Div('Résumé statistique par quintile', className='section-title'),
                html.Div(
                    className='note-box',
                    style={'marginBottom': '10px'},
                    children=["★ Rdt 2025 = test prédictif de référence (score publié début 2025)"]
                ),
                html.Div(className='card', children=[
                    dash_table.DataTable(
                        data=rows_t,
                        columns=[{'name': c, 'id': c} for c in rows_t[0].keys()],
                        style_table={'overflowX': 'auto'},
                        style_cell={
                            'backgroundColor': '#0d1117',
                            'color': '#c9d1d9',
                            'fontSize': '12px',
                            'fontFamily': 'IBM Plex Mono, monospace',
                            'border': '0.5px solid #21262d',
                            'padding': '8px 14px',
                            'textAlign': 'right',
                        },
                        style_header={
                            'backgroundColor': '#161b22',
                            'color': '#6e7681',
                            'fontSize': '10px',
                            'fontWeight': '400',
                            'textTransform': 'uppercase',
                            'letterSpacing': '0.07em',
                            'border': '0.5px solid #21262d',
                            'textAlign': 'left',
                        },
                        style_data_conditional=[
                            {
                                'if': {'column_id': 'Quintile'},
                                'textAlign': 'left',
                                'fontFamily': 'IBM Plex Sans, sans-serif',
                                'fontWeight': '500',
                            },
                            *[{
                                'if': {'filter_query': f'{{Quintile}} = {q}'},
                                'borderLeft': f'2px solid {color}',
                            } for q, color in [
                                ('Q5', '#3fb950'), ('Q4', '#56d364'),
                                ('Q3', '#8b949e'), ('Q2', '#d29922'), ('Q1', '#f85149'),
                            ]],
                        ],
                    ),
                ]),
            ])
        else:
            quintile_table = html.Div(
                html.Div("Aucune donnée quintile disponible.", className='note-box')
            )

    # ── Assemblage final ──────────────────────────────────────────────────────
    return html.Div([
        html.H2(titre, style={'fontSize': '18px', 'fontWeight': '500',
                              'color': '#e6edf3', 'marginBottom': '4px'}),
        html.P(sous,   style={'fontSize': '12px', 'color': '#6e7681',
                              'marginBottom': '20px'}),
        kpi_cards,
        methodo,
        rally_table,
        quintile_table,
    ])
