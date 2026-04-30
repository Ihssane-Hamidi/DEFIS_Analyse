"""
app.py — Point d'entrée principal
TPI · Analyse Financière (Dash + flask-login)
"""

import dash
from dash import Dash, dcc, html, Input, Output, State, callback
import dash_bootstrap_components as dbc
from flask import Flask, redirect, request
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    current_user,
)

from data import (
    load_mq, load_mq_prix, load_act, load_act_prix, load_brent,
    prepare_valid_mq, prepare_valid_act,
    PERIODS_LABELS,
)
from utils import detect_oil_rallies
from data import load_ca, load_ca_prix, prepare_valid_ca

# ── PAGES ─────────────────────────────────────────────────────────────────────
from pages.accueil     import layout as layout_accueil
from pages.societe     import layout as layout_societe,     register_callbacks as cb_societe
from pages.panel       import layout as layout_panel
from pages.brent       import layout as layout_brent,       register_callbacks as cb_brent
from pages.ols         import layout as layout_ols,         register_callbacks as cb_ols
from pages.strategique import layout as layout_strategique, register_callbacks as cb_strategique
from pages.composite   import layout as layout_composite,   register_callbacks as cb_composite


# ══════════════════════════════════════════════════════════════════════════════
# FLASK + LOGIN
# ══════════════════════════════════════════════════════════════════════════════
server = Flask(__name__)
server.secret_key = 'ihssane123'

login_manager = LoginManager()
login_manager.init_app(server)
login_manager.login_view = '/login'

USERS = {
    'admin':   {'password': 'admin123',   'role': 'Admin',   'display': 'Administrateur'},
    'analyst': {'password': 'analyst123', 'role': 'Analyst', 'display': 'I. Hamidi'},
    'viewer':  {'password': 'viewer123',  'role': 'Viewer',  'display': 'Lecteur'},
}


class User(UserMixin):
    def __init__(self, username):
        self.id      = username
        self.role    = USERS[username]['role']
        self.display = USERS[username]['display']


@login_manager.user_loader
def load_user(username):
    if username in USERS:
        return User(username)
    return None


# ── PROTECTION SYSTÉMATIQUE DE TOUTES LES ROUTES ─────────────────────────────
@server.before_request
def require_login():
    allowed = ['/login', '/logout', '/_dash-', '/assets', '/debug']
    if any(request.path.startswith(p) for p in allowed):
        return
    if not current_user.is_authenticated:
        return redirect('/login')


# ══════════════════════════════════════════════════════════════════════════════
# CHARGEMENT DONNÉES (au démarrage)
# ══════════════════════════════════════════════════════════════════════════════
print("Chargement des données...")
try:
    df_mq      = load_mq()
    prices_mq  = load_mq_prix()
    df_act     = load_act()
    prices_act = load_act_prix()
    brent      = load_brent()
    rallies    = detect_oil_rallies(brent)
    valid_mq   = prepare_valid_mq(df_mq)
    valid_act  = prepare_valid_act(df_act)
    df_ca      = load_ca()
    prices_ca  = load_ca_prix()
    valid_ca   = prepare_valid_ca(df_ca)
    print(f"MQ : {len(valid_mq)} entreprises · ACT : {len(valid_act)} entreprises · Rallies Brent : {len(rallies)}")
except Exception as e:
    import traceback
    traceback.print_exc()
    raise  # on stoppe si les données ne chargent pas

# Colonnes dynamiques ACT
col_score_act   = 'Score global - Performance Score /100'
col_secteur_act = 'Secteur'
col_narr_act    = 'Score global - Narrative Score'
col_trend_act   = 'Score global - Trend Score'
col_score_ca   = 'Score_global_CA'          
col_secteur_ca = 'Sector'   


# ══════════════════════════════════════════════════════════════════════════════
# DASH APP
# ══════════════════════════════════════════════════════════════════════════════
app = Dash(
    __name__,
    server=server,
    url_base_pathname='/',
    suppress_callback_exceptions=True,
    external_stylesheets=[],
)
app.title = "DEFIS · Analyse Financière"

APP_DATA = {
    'df_mq':           df_mq,
    'prices_mq':       prices_mq,
    'df_act':          df_act,
    'prices_act':      prices_act,
    'brent':           brent,
    'rallies':         rallies,
    'valid_mq':        valid_mq,
    'valid_act':       valid_act,
    'col_score_act':   col_score_act,
    'col_secteur_act': col_secteur_act,
    'col_narr_act':    col_narr_act,
    'col_trend_act':   col_trend_act,
    'df_ca':          df_ca,
    'prices_ca':      prices_ca,
    'valid_ca':       valid_ca,
    'col_score_ca':   col_score_ca,
    'col_secteur_ca': col_secteur_ca,
}


# ══════════════════════════════════════════════════════════════════════════════
# LAYOUT
# ══════════════════════════════════════════════════════════════════════════════
NAV_ITEMS = [
    ('Accueil',           'accueil',     ''),
    ('Société',           'societe',     str(len(valid_mq))),
    ('Panel Quintiles',   'panel',       ''),
    ('Analyse Brent',     'brent',       ''),
    ('Régression OLS',    'ols',         ''),
    ('Narrative / Trend', 'strategique', ''),
    ('Score Composite',   'composite',   ''),
]


def sidebar(username='', role='', display=''):
    initials = ''.join([p[0].upper() for p in display.split()[:2]]) if display else 'TPI'
    return html.Div(className='sidebar', children=[

        html.Div(className='sidebar-header', children=[
            html.Div(className='logo-row', children=[
                html.Div('T', className='logo-mark'),
                html.Div([
                    html.Div('TPI · Finance', className='logo-text'),
                    html.Div('Analyse 2025',  className='logo-sub'),
                ]),
            ]),
        ]),

        html.Div('Référentiel', className='ds-section'),
        html.Div(className='ds-toggle', children=[
            html.Div(
                dcc.RadioItems(
                    id='radio-dataset',
                    options=[
                        {'label': 'MQ',  'value': 'mq'},
                        {'label': 'ACT', 'value': 'act'},
                        {'label': 'CA',  'value': 'ca'},
                    ],
               
                    value='mq',
                    inline=True,
                    inputStyle={'display': 'none'},
                    labelStyle={
                        'flex': '1', 'textAlign': 'center',
                        'padding': '5px 6px', 'fontSize': '11px',
                        'cursor': 'pointer', 'borderRadius': '4px',
                        'color': '#8b949e',
                    },
                    labelClassName='ds-btn',
                )
            ),
        ]),

        html.Div('Vues', className='nav-section-label'),
        *[
            dcc.Link(
                href=f'/{page}',
                className='nav-link',
                id=f'nav-{page}',
                children=[
                    html.Span(label),
                    html.Span(badge, className='nav-badge') if badge else None,
                ],
            )
            for label, page, badge in NAV_ITEMS[:4]
        ],

        html.Div('Modèles', className='nav-section-label'),
        *[
            dcc.Link(
                href=f'/{page}',
                className='nav-link',
                id=f'nav-{page}',
                children=[html.Span(label)],
            )
            for label, page, badge in NAV_ITEMS[4:]
        ],

        html.Div(className='sidebar-footer', children=[
            html.Div(className='user-card', children=[
                html.Div(initials, className='avatar'),
                html.Div([
                    html.Div(display or username, className='user-name'),
                    html.Div(role, className='user-role'),
                ]),
                html.A('↩', href='/logout', className='logout-btn'),
            ]),
        ]),
    ])


def topbar(page_name='Accueil', dataset_label='Management Quality', badge_class='dataset-badge-mq'):
    return html.Div(className='topbar', children=[
        html.Div(className='breadcrumb', children=[
            html.Span('TPI'),
            html.Span('/', className='breadcrumb-sep'),
            html.Span(dataset_label, id='breadcrumb-dataset'),
            html.Span('/', className='breadcrumb-sep'),
            html.Span(page_name, className='breadcrumb-active', id='breadcrumb-page'),
        ]),
        html.Div(className='topbar-actions', children=[
            html.Span(dataset_label, className=badge_class, id='dataset-badge'),
        ]),
    ])


app.layout = html.Div([
    dcc.Location(id='url', refresh=False),
    dcc.Store(id='store-dataset', data='mq', storage_type='session'),
    dcc.Store(id='store-page',    data='accueil'),
    html.Div(id='app-container'),
])


# ══════════════════════════════════════════════════════════════════════════════
# CALLBACKS
# ══════════════════════════════════════════════════════════════════════════════
@app.callback(
    Output('store-dataset', 'data'),
    Input('radio-dataset', 'value'),
    prevent_initial_call=True,
)
def update_dataset_store(value):
    return value


@app.callback(
    Output('app-container', 'children'),
    Input('url', 'pathname'),
    State('store-dataset', 'data'),
)
def route(pathname, dataset):
    if pathname in ('/', '/login', None):
        pathname = '/accueil'

    # Dans la fonction route()
    is_mq  = (dataset == 'mq')
    is_act = (dataset == 'act')
    is_ca  = (dataset == 'ca')

    valid        = valid_mq  if is_mq else (valid_act  if is_act else valid_ca)
    prices       = prices_mq if is_mq else (prices_act if is_act else prices_ca)
    score_col    = 'Score_global_MQ'  if is_mq else (col_score_act  if is_act else col_score_ca)
    secteur_col  = 'Macro_Secteur'    if is_mq else (col_secteur_act if is_act else col_secteur_ca)
    quintile_col = 'Quintile_MQ'      if is_mq else ('Quintile_ACT'  if is_act else 'Quintile_CA')
    dataset_label= 'Management Quality' if is_mq else ('ACT — Transition Carbone' if is_act else 'CA')
    badge_class  = 'dataset-badge-mq'   if is_mq else ('dataset-badge-act' if is_act else 'dataset-badge-ca')

    page_map = {
        '/accueil':     ('Accueil',           layout_accueil),
        '/societe':     ('Société',           layout_societe),
        '/panel':       ('Panel Quintiles',   layout_panel),
        '/brent':       ('Analyse Brent',     layout_brent),
        '/ols':         ('Régression OLS',    layout_ols),
        '/strategique': ('Narrative / Trend', layout_strategique),
        '/composite':   ('Score Composite',   layout_composite),
    }

    page_name, layout_fn = page_map.get(pathname, ('Accueil', layout_accueil))

    ctx = {
        **APP_DATA,
        'is_mq':        is_mq,
        'valid':        valid,
        'prices':       prices,
        'score_col':    score_col,
        'secteur_col':  secteur_col,
        'quintile_col': quintile_col,
        'pct_col':      pct_col,
        'dataset_label': dataset_label,
    }

    return html.Div(className='app-shell', children=[
        sidebar(
            username=current_user.id      if current_user.is_authenticated else '',
            role=current_user.role        if current_user.is_authenticated else '',
            display=current_user.display  if current_user.is_authenticated else '',
        ),
        html.Div(className='main-content', children=[
            topbar(page_name, dataset_label, badge_class),
            html.Div(className='page-content', children=[
                dcc.Loading(
                    type='circle',
                    color='#1f6feb',
                    children=layout_fn(ctx),
                ),
            ]),
        ]),
    ])


# ── Callbacks des pages ────────────────────────────────────────────────────────
cb_societe(app,     APP_DATA)
cb_brent(app,       APP_DATA)
cb_ols(app,         APP_DATA)
cb_strategique(app, APP_DATA)
cb_composite(app,   APP_DATA)


# ══════════════════════════════════════════════════════════════════════════════
# ROUTES FLASK (login / logout)
# ══════════════════════════════════════════════════════════════════════════════
@server.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username  = request.form.get('username', '').strip()
        password  = request.form.get('password', '').strip()
        user_data = USERS.get(username)
        if user_data and user_data['password'] == password:
            login_user(User(username), remember=True)
            return redirect('/')
        return _login_page('Identifiants incorrects.')
    return _login_page()


@server.route('/logout')
def logout():
    logout_user()
    return redirect('/login')


def _login_page(error=None):
    error_html = f'<div class="login-error">{error}</div>' if error else ''
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <title>TPI · Connexion</title>
  <link rel="stylesheet" href="/assets/style.css">
</head>
<body>
<div class="login-shell">
  <div class="login-card">
    <div class="login-logo">
      <div class="logo-mark">T</div>
      <div>
        <div class="logo-text">TPI · Finance</div>
        <div class="logo-sub">Analyse 2025</div>
      </div>
    </div>
    <div class="login-title">Connexion</div>
    <div class="login-sub">Accès réservé aux membres TPI</div>
    {error_html}
    <form method="POST">
      <label class="login-label">Identifiant</label>
      <input class="login-input" type="text" name="username" placeholder="ex: analyst" autofocus>
      <label class="login-label">Mot de passe</label>
      <input class="login-input" type="password" name="password" placeholder="••••••••">
      <button class="login-btn" type="submit">Se connecter</button>
    </form>
  </div>
</div>
</body>
</html>"""


# ══════════════════════════════════════════════════════════════════════════════
# DEBUG ROUTE
# ══════════════════════════════════════════════════════════════════════════════
@server.route('/debug')
def debug():
    import traceback
    lines = []

    lines.append(f"valid_mq : {len(valid_mq)} lignes")
    lines.append(f"valid_act : {len(valid_act)} lignes")
    lines.append(f"Colonnes MQ : {list(valid_mq.columns)}")
    lines.append(f"Colonnes ACT : {list(valid_act.columns)}")

    from utils import prepare_ols_data, run_ols
    try:
        dep    = 'Rendement_2025'
        df_test = valid_mq[['Score_global_MQ', 'Macro_Secteur', dep,
                             'LogMarketCap', 'BookToMarket', 'Quintile_MQ']].dropna()
        lines.append(f"OLS MQ df_test : {len(df_test)} lignes après dropna")
        df_p = prepare_ols_data(df_test, 'Score_global_MQ', 'Macro_Secteur')
        m    = run_ols(df_p, dep, 'Macro_Secteur', 'simple')
        lines.append(f"OLS MQ résultat : {m}")
    except Exception:
        lines.append(f"OLS MQ ERREUR : {traceback.format_exc()}")

    try:
        dep     = 'Rendement_2025'
        df_test = valid_act[[col_score_act, col_secteur_act, dep,
                              'LogMarketCap', 'BookToMarket']].dropna()
        lines.append(f"OLS ACT df_test : {len(df_test)} lignes après dropna")
    except Exception:
        lines.append(f"OLS ACT ERREUR : {traceback.format_exc()}")

    lines.append(f"Rendement_2025 MQ sample : {valid_mq['Rendement_2025'].dropna().head().tolist()}")

    return '<br>'.join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# LANCEMENT
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    app.run(debug=True, port=8050)
