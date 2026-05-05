"""
pages/admin.py — Page d'administration
Upload xlsx → pipeline → parquet → Google Drive
Accessible uniquement à l'utilisateur admin.
"""

import base64
import json
import threading

from dash import html, dcc, Input, Output, State, callback, no_update
import dash_bootstrap_components as dbc

# Cache ticker partagé en mémoire (persist pendant la session serveur)
_ticker_cache = {}
_pipeline_lock = threading.Lock()

# État du pipeline (thread-safe via dcc.Store)
PIPELINE_IDLE    = 'idle'
PIPELINE_RUNNING = 'running'
PIPELINE_DONE    = 'done'
PIPELINE_ERROR   = 'error'

DATASET_OPTIONS = [
    {'label': '📊 TPI Management Quality (MQ)',   'value': 'mq'},
    {'label': '🌿 ACT — Low Carbon Transition',   'value': 'act'},
    {'label': '🌍 Climate Action 100+ (CA)',       'value': 'ca'},
    {'label': '🌡️ Carbon Performance (CP)',        'value': 'cp'},
]

CURRENT_YEAR = 2025
MIN_YEAR     = 2018


# ══════════════════════════════════════════════════════════════════════════════
# LAYOUT
# ══════════════════════════════════════════════════════════════════════════════

def layout(ctx: dict):
    return html.Div([

        # ── Titre ─────────────────────────────────────────────────────────
        html.H2('Administration · Mise à jour des données',
                style={'fontSize': '18px', 'fontWeight': '500',
                       'color': '#e6edf3', 'marginBottom': '4px'}),
        html.P('Upload d\'un fichier xlsx → génération automatique du parquet → sauvegarde Drive',
               style={'fontSize': '12px', 'color': '#6e7681', 'marginBottom': '24px'}),

        # ── Stores ────────────────────────────────────────────────────────
        dcc.Store(id='admin-pipeline-state', data={'status': PIPELINE_IDLE, 'log': []}),
        dcc.Store(id='admin-file-store',     data=None),
        dcc.Interval(id='admin-poll', interval=1500, disabled=True),

        # ── Formulaire ────────────────────────────────────────────────────
        html.Div(className='card', style={'marginBottom': '20px'}, children=[

            # Sélection dataset
            html.Div([
                html.Label('Type de dataset', className='kpi-label',
                           style={'marginBottom': '8px', 'display': 'block'}),
                dcc.Dropdown(
                    id='admin-dataset-type',
                    options=DATASET_OPTIONS,
                    value='mq',
                    clearable=False,
                    style={
                        'backgroundColor': '#161b22',
                        'color': '#c9d1d9',
                        'border': '0.5px solid #30363d',
                        'fontSize': '13px',
                    }
                ),
            ], style={'marginBottom': '20px'}),

            # Sélection années
            html.Div([
                html.Label('Années à inclure', className='kpi-label',
                           style={'marginBottom': '8px', 'display': 'block'}),
                html.Div(id='admin-years-display',
                         style={'fontSize': '12px', 'color': '#58a6ff',
                                'marginBottom': '8px'}),
                dcc.RangeSlider(
                    id='admin-years-slider',
                    min=MIN_YEAR,
                    max=CURRENT_YEAR,
                    step=1,
                    value=[2023, CURRENT_YEAR],
                    marks={y: {'label': str(y), 'style': {'color': '#6e7681', 'fontSize': '11px'}}
                           for y in range(MIN_YEAR, CURRENT_YEAR + 1)},
                    tooltip={'placement': 'bottom', 'always_visible': False},
                ),
            ], style={'marginBottom': '24px'}),

            # Upload xlsx
            html.Div([
                html.Label('Fichier xlsx', className='kpi-label',
                           style={'marginBottom': '8px', 'display': 'block'}),
                dcc.Upload(
                    id='admin-upload',
                    children=html.Div([
                        html.Div('📂', style={'fontSize': '32px', 'marginBottom': '8px'}),
                        html.Div('Glisser-déposer ou ', style={'display': 'inline'}),
                        html.A('sélectionner un fichier xlsx',
                               style={'color': '#58a6ff', 'cursor': 'pointer'}),
                        html.Div('Formats acceptés : .xlsx',
                                 style={'fontSize': '11px', 'color': '#6e7681',
                                        'marginTop': '6px'}),
                    ], style={'textAlign': 'center', 'padding': '20px'}),
                    style={
                        'border': '1px dashed #30363d',
                        'borderRadius': '8px',
                        'backgroundColor': '#0d1117',
                        'cursor': 'pointer',
                        'transition': 'border-color 0.2s',
                    },
                    accept='.xlsx',
                    multiple=False,
                ),
                html.Div(id='admin-upload-status',
                         style={'fontSize': '12px', 'color': '#3fb950',
                                'marginTop': '8px'}),
            ], style={'marginBottom': '24px'}),

            # Bouton lancer
            html.Button(
                '⚡ Lancer le pipeline',
                id='admin-run-btn',
                disabled=True,
                style={
                    'backgroundColor': '#238636',
                    'color': '#ffffff',
                    'border': 'none',
                    'borderRadius': '6px',
                    'padding': '10px 20px',
                    'fontSize': '13px',
                    'cursor': 'pointer',
                    'fontFamily': 'IBM Plex Sans, sans-serif',
                    'opacity': '0.5',
                }
            ),
        ]),

        # ── Console de progression ─────────────────────────────────────────
        html.Div(id='admin-console-wrapper', children=[
            html.Div('Progression', className='section-title'),
            html.Div(
                id='admin-console',
                style={
                    'backgroundColor': '#0d1117',
                    'border': '0.5px solid #21262d',
                    'borderRadius': '6px',
                    'padding': '12px 16px',
                    'fontFamily': 'IBM Plex Mono, monospace',
                    'fontSize': '12px',
                    'color': '#c9d1d9',
                    'minHeight': '120px',
                    'maxHeight': '320px',
                    'overflowY': 'auto',
                    'lineHeight': '1.8',
                },
                children=[html.Div('En attente...', style={'color': '#6e7681'})]
            ),
        ]),

        # ── Résumé final ──────────────────────────────────────────────────
        html.Div(id='admin-result-summary'),

    ], style={'maxWidth': '720px', 'margin': '0 auto'})


# ══════════════════════════════════════════════════════════════════════════════
# CALLBACKS
# ══════════════════════════════════════════════════════════════════════════════

def register_callbacks(app):
    """Enregistre tous les callbacks de la page admin."""

    # ── Affichage années sélectionnées ────────────────────────────────────
    @app.callback(
        Output('admin-years-display', 'children'),
        Input('admin-years-slider', 'value'),
    )
    def update_years_display(value):
        if not value:
            return ''
        start, end = value
        years = list(range(start, end + 1))
        return f"Années sélectionnées : {', '.join(map(str, years))} ({len(years)} année(s))"

    # ── Réception fichier xlsx ────────────────────────────────────────────
    @app.callback(
        Output('admin-upload-status', 'children'),
        Output('admin-file-store',    'data'),
        Output('admin-run-btn',       'disabled'),
        Output('admin-run-btn',       'style'),
        Input('admin-upload',         'contents'),
        State('admin-upload',         'filename'),
    )
    def on_file_upload(contents, filename):
        btn_disabled_style = {
            'backgroundColor': '#238636', 'color': '#ffffff',
            'border': 'none', 'borderRadius': '6px',
            'padding': '10px 20px', 'fontSize': '13px',
            'cursor': 'pointer', 'fontFamily': 'IBM Plex Sans, sans-serif',
            'opacity': '0.5',
        }
        btn_active_style = {**btn_disabled_style, 'opacity': '1', 'cursor': 'pointer'}

        if not contents:
            return '', None, True, btn_disabled_style

        if not filename.endswith('.xlsx'):
            return (
                f'❌ Fichier invalide : {filename} (attendu .xlsx)',
                None, True, btn_disabled_style
            )

        return (
            f'✅ Fichier chargé : {filename}',
            contents,
            False,
            btn_active_style,
        )

    # ── Lancement pipeline ────────────────────────────────────────────────
    @app.callback(
        Output('admin-pipeline-state', 'data'),
        Output('admin-poll',           'disabled'),
        Input('admin-run-btn',         'n_clicks'),
        State('admin-file-store',      'data'),
        State('admin-dataset-type',    'value'),
        State('admin-years-slider',    'value'),
        State('admin-pipeline-state',  'data'),
        prevent_initial_call=True,
    )
    def start_pipeline(n_clicks, file_contents, dataset_type, years_range, current_state):
        if not n_clicks or not file_contents:
            return no_update, True

        if current_state.get('status') == PIPELINE_RUNNING:
            return no_update, False  # déjà en cours

        # Décode le fichier
        try:
            _, content_str = file_contents.split(',')
            file_bytes = base64.b64decode(content_str)
        except Exception as e:
            return {'status': PIPELINE_ERROR, 'log': [f'Erreur décodage fichier : {e}']}, True

        years = list(range(years_range[0], years_range[1] + 1))
        state = {'status': PIPELINE_RUNNING, 'log': ['🚀 Pipeline démarré...']}

        # Lance le pipeline dans un thread séparé pour ne pas bloquer Dash
        def run():
            from pipeline.builder import run_pipeline

            log_lines = ['🚀 Pipeline démarré...']

            def progress(step, done=0, total=0):
                icons = {
                    'parse':        '📄 Lecture du fichier xlsx...',
                    'tickers':      f'🔍 Résolution tickers ({done}/{total})...',
                    'prix':         f'📈 Téléchargement prix bloc {done}/{total}...',
                    'fondamentaux': f'💰 Fondamentaux ({done}/{total})...',
                    'métriques':    '📊 Calcul métriques financières...',
                    'fusion':       '🔗 Fusion des données...',
                    'drive':        '☁️ Sauvegarde sur Google Drive...',
                    'terminé':      '✅ Pipeline terminé avec succès !',
                    'erreur':       '❌ Erreur pendant le pipeline.',
                }
                msg = icons.get(step, f'⚙️ {step}...')
                if msg not in log_lines:
                    log_lines.append(msg)

            result = run_pipeline(
                file_bytes    = file_bytes,
                dataset_type  = dataset_type,
                years         = years,
                ticker_cache  = _ticker_cache,
                progress_cb   = progress,
                save_to_drive = True,
            )

            # Stocke le résultat dans un fichier tmp lisible par le callback poll
            summary = {
                'status':    PIPELINE_DONE if result['success'] else PIPELINE_ERROR,
                'log':       log_lines,
                'n_total':   result['n_total'],
                'n_tickers': result['n_tickers'],
                'n_fin':     result['n_fin'],
                'error':     result['error'],
            }
            import tempfile, json
            with open('/tmp/admin_pipeline_result.json', 'w') as f:
                json.dump(summary, f)

        thread = threading.Thread(target=run, daemon=True)
        thread.start()

        return state, False  # active le polling

    # ── Polling progression ───────────────────────────────────────────────
    @app.callback(
        Output('admin-console',        'children'),
        Output('admin-result-summary', 'children'),
        Output('admin-poll',           'disabled', allow_duplicate=True),
        Input('admin-poll',            'n_intervals'),
        State('admin-pipeline-state',  'data'),
        prevent_initial_call=True,
    )
    def poll_pipeline(n_intervals, state):
        import os

        result_file = '/tmp/admin_pipeline_result.json'
        if not os.path.exists(result_file):
            # Pipeline encore en cours
            log = state.get('log', [])
            console = [html.Div(line) for line in log] or [html.Div('En cours...', style={'color': '#6e7681'})]
            return console, '', False

        # Résultat disponible
        try:
            with open(result_file) as f:
                summary = json.load(f)
            os.unlink(result_file)
        except Exception:
            return [html.Div('Erreur lecture résultat')], '', True

        log_lines = summary.get('log', [])
        console   = [html.Div(line, style={
            'color': '#3fb950' if '✅' in line
                     else '#f85149' if '❌' in line
                     else '#c9d1d9'
        }) for line in log_lines]

        # Résumé final
        if summary['status'] == PIPELINE_DONE:
            result_block = html.Div(className='card', style={'marginTop': '20px'}, children=[
                html.Div('Résumé', className='section-title'),
                html.Div(className='kpi-grid', children=[
                    _kpi('Entreprises total',    str(summary['n_total']),   '#58a6ff'),
                    _kpi('Tickers trouvés',      str(summary['n_tickers']), '#3fb950'),
                    _kpi('Avec données fin.',    str(summary['n_fin']),     '#a78bfa'),
                ]),
                html.Div('✅ Parquets sauvegardés sur Google Drive.',
                         className='note-box', style={'marginTop': '12px'}),
            ])
        else:
            error_msg = summary.get('error', 'Erreur inconnue')
            result_block = html.Div(
                className='warn-box',
                style={'marginTop': '20px'},
                children=[
                    html.Strong('❌ Erreur pipeline :'),
                    html.Pre(error_msg, style={'fontSize': '11px', 'marginTop': '8px',
                                               'whiteSpace': 'pre-wrap'}),
                ]
            )

        return console, result_block, True  # stoppe le polling


def _kpi(label, value, color):
    return html.Div(className='kpi-card', children=[
        html.Div(label, className='kpi-label'),
        html.Div(value, className='kpi-value', style={'color': color}),
    ])
