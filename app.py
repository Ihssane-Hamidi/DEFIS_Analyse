"""
app.py — Point d'entrée principal
DEFIS · Analyse Financière (Dash + flask-login)
"""
import os
import pandas as pd
import dash
from dash import Dash, dcc, html, Input, Output, State, callback
import dash_bootstrap_components as dbc
from flask import Flask, redirect, request
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    current_user,
)

from data import (
    load_mq, load_mq_prix, load_act, load_act_prix,
    load_ca, load_ca_prix,
    load_cp, load_cp_prix,
    load_brent,
    prepare_valid_mq, prepare_valid_act,
    prepare_valid_ca, prepare_valid_cp,
    PERIODS_LABELS,
)
from utils import detect_oil_rallies, calc_metriques_brent

# ── PAGES ─────────────────────────────────────────────────────────────────────
from pages.accueil     import layout as layout_accueil
from pages.societe     import layout as layout_societe,     register_callbacks as cb_societe
from pages.panel       import layout as layout_panel
from pages.brent       import layout as layout_brent,       register_callbacks as cb_brent
from pages.ols         import layout as layout_ols,         register_callbacks as cb_ols
from pages.strategique import layout as layout_strategique, register_callbacks as cb_strategique
from pages.composite   import layout as layout_composite,   register_callbacks as cb_composite
from pages.admin       import layout as layout_admin,       register_callbacks as cb_admin


# ══════════════════════════════════════════════════════════════════════════════
# FLASK + LOGIN
# ══════════════════════════════════════════════════════════════════════════════
server = Flask(__name__)
server.secret_key = os.environ.get('SECRET_KEY', 'fallback-local-dev')

login_manager = LoginManager()
login_manager.init_app(server)
login_manager.login_view = '/login'

USERS = {
    'admin-ADEME': {'password': 'admin123',   'role': 'Admin',   'display': 'Administrateur'},
    'analyst1':    {'password': 'analyst123', 'role': 'Analyst', 'display': 'I. Hamidi'},
    'Mathieu':     {'password': 'analyst123', 'role': 'Analyst', 'display': 'Mathieu'},
    'Stan':        {'password': 'analyst123', 'role': 'Analyst', 'display': 'Stan'},
    'viewer':      {'password': 'viewer123',  'role': 'Viewer',  'display': 'Lecteur'},
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
def _safe_brent(prices, valid, rallies):
    if (valid is None or valid.empty
            or prices is None or (hasattr(prices, 'empty') and prices.empty)
            or not rallies
            or 'ticker' not in valid.columns):
        return {}, {}
    tickers = valid['ticker'].dropna().str.strip().tolist()
    if not tickers:
        return {}, {}
    return calc_metriques_brent(prices, tickers, rallies)
    
print("Chargement des données...")

# Valeurs par défaut — l'app démarre même si tout est vide
df_mq = df_act = df_ca = df_cp = pd.DataFrame()
prices_mq = prices_act = prices_ca = prices_cp = pd.DataFrame()
valid_mq = valid_act = valid_ca = valid_cp = pd.DataFrame()
brent = pd.Series(dtype=float)
rallies = []
rdt_b_mq = vol_b_mq = {}
rdt_b_act = vol_b_act = {}
rdt_b_ca = vol_b_ca = {}
rdt_b_cp = vol_b_cp = {}

try:
    df_mq      = load_mq();      df_mq      = pd.DataFrame() if df_mq      is None else df_mq
    prices_mq  = load_mq_prix(); prices_mq  = pd.DataFrame() if prices_mq  is None else prices_mq
    df_act     = load_act();     df_act     = pd.DataFrame() if df_act     is None else df_act
    prices_act = load_act_prix();prices_act = pd.DataFrame() if prices_act is None else prices_act
    df_ca      = load_ca();      df_ca      = pd.DataFrame() if df_ca      is None else df_ca
    prices_ca  = load_ca_prix(); prices_ca  = pd.DataFrame() if prices_ca  is None else prices_ca
    df_cp      = load_cp();      df_cp      = pd.DataFrame() if df_cp      is None else df_cp
    prices_cp  = load_cp_prix(); prices_cp  = pd.DataFrame() if prices_cp  is None else prices_cp

    if isinstance(brent, pd.Series) and len(brent) > 0 and isinstance(brent.index, pd.DatetimeIndex):
        rallies = detect_oil_rallies(brent)
    else:
        rallies = []

    valid_mq  = prepare_valid_mq(df_mq)
    valid_act = prepare_valid_act(df_act)
    valid_ca  = prepare_valid_ca(df_ca)
    valid_cp  = prepare_valid_cp(df_cp) if not df_cp.empty else pd.DataFrame()

    rdt_b_mq,  vol_b_mq  = _safe_brent(prices_mq,  valid_mq,  rallies)
    rdt_b_act, vol_b_act  = _safe_brent(prices_act, valid_act, rallies)
    rdt_b_ca,  vol_b_ca   = _safe_brent(prices_ca,  valid_ca,  rallies)
    rdt_b_cp,  vol_b_cp   = _safe_brent(prices_cp,  valid_cp,  rallies)

    print(f"MQ : {len(valid_mq)} · ACT : {len(valid_act)} · "
          f"CA : {len(valid_ca)} · CP : {len(valid_cp)} · "
          f"Rallies : {len(rallies)}")
    print("Cache Brent OK")

except Exception as e:
    import traceback
    print("⚠️ ERREUR CHARGEMENT DONNÉES (app continue avec données vides) :")
    traceback.print_exc() 
    # On ne raise pas — l'app démarre quand même

# ══════════════════════════════════════════════════════════════════════════════
# COLONNES DYNAMIQUES
# ══════════════════════════════════════════════════════════════════════════════
col_score_act   = 'Score global - Performance Score /100'
col_secteur_act = 'Secteur'
col_narr_act    = 'Score global - Narrative Score'
col_trend_act   = 'Score global - Trend Score'

col_score_ca    = 'Score_global_CA'
col_secteur_ca  = 'Sector'
col_quintile_ca = 'Quintile_CA'
col_pct_ca      = 'CA_percentile'

col_score_cp    = 'Score_global_CP'
col_secteur_cp  = 'Macro_Secteur'
col_quintile_cp = 'Quintile_CP'
col_pct_cp      = 'CP_percentile'


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
    # ── DataFrames bruts ──────────────────────────────────────────────────────
    'df_mq':            df_mq,
    'df_act':           df_act,
    'df_ca':            df_ca,
    'df_cp':            df_cp if df_cp is not None else pd.DataFrame(),

    # ── Prix journaliers ──────────────────────────────────────────────────────
    'prices_mq':        prices_mq,
    'prices_act':       prices_act,
    'prices_ca':        prices_ca,
    'prices_cp':        prices_cp if prices_cp is not None else pd.DataFrame(),

    # ── Valides (filtrés ticker + rendement) ──────────────────────────────────
    'valid_mq':         valid_mq,
    'valid_act':        valid_act,
    'valid_ca':         valid_ca,
    'valid_cp':         valid_cp,

    # ── Brent ─────────────────────────────────────────────────────────────────
    'brent':            brent,
    'rallies':          rallies,

    # ── Métriques Brent par dataset ───────────────────────────────────────────
    'rdt_b_mq':         rdt_b_mq,
    'vol_b_mq':         vol_b_mq,
    'rdt_b_act':        rdt_b_act,
    'vol_b_act':        vol_b_act,
    'rdt_b_ca':         rdt_b_ca,
    'vol_b_ca':         vol_b_ca,
    'rdt_b_cp':         rdt_b_cp,
    'vol_b_cp':         vol_b_cp,

    # ── Colonnes ACT ──────────────────────────────────────────────────────────
    'col_score_act':    col_score_act,
    'col_secteur_act':  col_secteur_act,
    'col_narr_act':     col_narr_act,
    'col_trend_act':    col_trend_act,

    # ── Colonnes CA ───────────────────────────────────────────────────────────
    'col_score_ca':     col_score_ca,
    'col_secteur_ca':   col_secteur_ca,
    'col_quintile_ca':  col_quintile_ca,
    'col_pct_ca':       col_pct_ca,

    # ── Colonnes CP ───────────────────────────────────────────────────────────
    'col_score_cp':     col_score_cp,
    'col_secteur_cp':   col_secteur_cp,
    'col_quintile_cp':  col_quintile_cp,
    'col_pct_cp':       col_pct_cp,
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
    is_admin = (role == 'Admin')

    nav_links = []
    for label, page, badge in NAV_ITEMS:
        nav_links.append(
            dcc.Link(
                href=f'/{page}',
                className='nav-item',
                children=[
                    html.Span(label, className='nav-label'),
                    html.Span(badge, className='nav-badge') if badge else None,
                ],
            )
        )

    # Lien admin uniquement pour le rôle Admin
    if is_admin:
        nav_links.append(
            dcc.Link(
                href='/admin',
                className='nav-item nav-item-admin',
                children=[
                    html.Span('⚙ Administration', className='nav-label'),
                ],
            )
        )

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
                        {'label': 'CP',  'value': 'cp'},
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
        *nav_links,

        # Pied de sidebar : utilisateur connecté
        html.Div(className='sidebar-footer', children=[
            html.Div(className='user-chip', children=[
                html.Div(initials, className='user-avatar'),
                html.Div([
                    html.Div(display or username, className='user-name'),
                    html.Div(role,                className='user-role'),
                ]),
            ]),
            dcc.Link('Déconnexion', href='/logout', className='logout-link'),
        ]),
    ])


def topbar(page_name, dataset_label, badge_class):
    return html.Div(className='topbar', children=[
        html.Div(className='breadcrumb', children=[
            html.Span('DEFIS', className='breadcrumb-root'),
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
    dcc.Store(id='store-dataset', data='mq', storage_type='local'),
    dcc.Store(id='store-page',    data='accueil'),
    html.Div(id='app-container'),
])


# ══════════════════════════════════════════════════════════════════════════════
# CALLBACKS
# ══════════════════════════════════════════════════════════════════════════════
@app.callback(
    Output('store-dataset', 'data'),
    Input('radio-dataset', 'value'),
)
def update_dataset_store(value):
    return value or 'mq'


@app.callback(
    Output('app-container', 'children'),
    Input('url', 'pathname'),
    Input('store-dataset', 'data'),
)
def route(pathname, dataset):
    if pathname in ('/', '/login', None):
        pathname = '/accueil'

    # ── Garde admin ───────────────────────────────────────────────────────────
    if pathname == '/admin':
        if not current_user.is_authenticated or current_user.role != 'Admin':
            return html.Div(
                html.Div('⛔ Accès réservé à l\'administrateur.',
                         className='warn-box'),
                style={'padding': '40px'}
            )

    dataset = dataset or 'mq'
    is_mq   = (dataset == 'mq')
    is_act  = (dataset == 'act')
    is_ca   = (dataset == 'ca')
    is_cp   = (dataset == 'cp')

    if is_mq:
        valid         = valid_mq
        prices        = prices_mq
        score_col     = 'Score_global_MQ'
        secteur_col   = 'Macro_Secteur'
        quintile_col  = 'Quintile_MQ'
        pct_col       = 'MQ_percentile'
        dataset_label = 'Management Quality'
        badge_class   = 'dataset-badge-mq'
    elif is_act:
        valid         = valid_act
        prices        = prices_act
        score_col     = col_score_act
        secteur_col   = col_secteur_act
        quintile_col  = 'Quintile_ACT'
        pct_col       = 'Score_percentile'
        dataset_label = 'ACT — Transition Carbone'
        badge_class   = 'dataset-badge-act'
    elif is_ca:
        valid         = valid_ca
        prices        = prices_ca
        score_col     = col_score_ca
        secteur_col   = col_secteur_ca
        quintile_col  = col_quintile_ca
        pct_col       = col_pct_ca
        dataset_label = 'CA — Climate Action'
        badge_class   = 'dataset-badge-ca'
    else:  # CP
        valid         = valid_cp
        prices        = prices_cp if prices_cp is not None else pd.DataFrame()
        score_col     = col_score_cp
        secteur_col   = col_secteur_cp
        quintile_col  = col_quintile_cp
        pct_col       = col_pct_cp
        dataset_label = 'CP — Carbon Performance'
        badge_class   = 'dataset-badge-cp'

    page_map = {
        '/accueil':     ('Accueil',           layout_accueil),
        '/societe':     ('Société',           layout_societe),
        '/panel':       ('Panel Quintiles',   layout_panel),
        '/brent':       ('Analyse Brent',     layout_brent),
        '/ols':         ('Régression OLS',    layout_ols),
        '/strategique': ('Narrative / Trend', layout_strategique),
        '/composite':   ('Score Composite',   layout_composite),
        '/admin':       ('Administration',    layout_admin),
    }

    page_name, layout_fn = page_map.get(pathname, ('Accueil', layout_accueil))

    ctx = {
        **APP_DATA,
        'is_mq':         is_mq,
        'is_act':        is_act,
        'is_ca':         is_ca,
        'is_cp':         is_cp,
        'valid':         valid,
        'prices':        prices,
        'score_col':     score_col,
        'secteur_col':   secteur_col,
        'quintile_col':  quintile_col,
        'pct_col':       pct_col,
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


# ── Callbacks des pages ───────────────────────────────────────────────────────
cb_societe(app,     APP_DATA)
cb_brent(app,       APP_DATA)
cb_ols(app,         APP_DATA)
cb_strategique(app, APP_DATA)
cb_composite(app,   APP_DATA)
cb_admin(app)


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
    lines.append(f"valid_mq  : {len(valid_mq)} lignes")
    lines.append(f"valid_act : {len(valid_act)} lignes")
    lines.append(f"valid_ca  : {len(valid_ca)} lignes")
    lines.append(f"valid_cp  : {len(valid_cp)} lignes")
    lines.append(f"Colonnes MQ  : {list(valid_mq.columns)}")
    lines.append(f"Colonnes ACT : {list(valid_act.columns)}")
    lines.append(f"Colonnes CA  : {list(valid_ca.columns)}")
    lines.append(f"Colonnes CP  : {list(valid_cp.columns) if not valid_cp.empty else 'vide'}")

    from utils import prepare_ols_data, run_ols
    try:
        dep     = 'Rendement_2025'
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
@server.route('/ping')
def ping():
    return 'ok', 200
    
if __name__ == '__main__':
    app.run(debug=True, port=8050)
