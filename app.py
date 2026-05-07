"""
app.py — Point d'entrée principal
DEFIS · Analyse Financière (Dash + flask-login)
"""
import os
import pandas as pd
from dash import Dash, dcc, html, Input, Output, State, no_update
from flask import Flask, redirect, request
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    current_user,
)
import traceback
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
    'admin-ADEME': {
        'password': os.environ.get('PWD_ADMIN',   'admin123'),
        'role': 'Admin',   'display': 'Administrateur',
    },
    'analyst1': {
        'password': os.environ.get('PWD_ANALYST', 'analyst123'),
        'role': 'Analyst', 'display': 'I. Hamidi',
    },
    'Mathieu': {
        'password': os.environ.get('PWD_ANALYST', 'analyst123'),
        'role': 'Analyst', 'display': 'Mathieu',
    },
    'Stan': {
        'password': os.environ.get('PWD_ANALYST', 'analyst123'),
        'role': 'Analyst', 'display': 'Stan',
    },
    'viewer': {
        'password': os.environ.get('PWD_VIEWER',  'viewer123'),
        'role': 'Viewer',  'display': 'Lecteur',
    },
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
    allowed = ['/login', '/logout', '/_dash-', '/assets', '/ping']
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

def _load_safe(fn, label):
    """Charge une source de données indépendamment — n'interrompt pas les autres."""
    try:
        result = fn()
        print(f"  ✓ {label}")
        return result
    except Exception:
        import traceback
        print(f"  ✗ {label} — données vides :")
        traceback.print_exc()
        return None

print("Chargement des données...")

df_mq     = _load_safe(load_mq,       'load_mq')      
prices_mq = _load_safe(load_mq_prix,  'load_mq_prix') 
df_act    = _load_safe(load_act,      'load_act')    
prices_act= _load_safe(load_act_prix, 'load_act_prix')
df_ca     = _load_safe(load_ca,       'load_ca')     
prices_ca = _load_safe(load_ca_prix,  'load_ca_prix') 
df_cp     = _load_safe(load_cp,       'load_cp')      
prices_cp = _load_safe(load_cp_prix,  'load_cp_prix')
brent     = _load_safe(load_brent,    'load_brent')   

rallies = []
if isinstance(brent, pd.Series) and len(brent) > 0 and isinstance(brent.index, pd.DatetimeIndex):
    try:
        rallies = detect_oil_rallies(brent)
    except Exception:
        print("  ✗ detect_oil_rallies — rallies vides")

valid_mq  = pd.DataFrame()
valid_act = pd.DataFrame()
valid_ca  = pd.DataFrame()
valid_cp  = pd.DataFrame()

try: valid_mq  = prepare_valid_mq(df_mq)
except Exception: traceback.print_exc()

try: valid_act = prepare_valid_act(df_act)
except Exception: traceback.print_exc()

try: valid_ca  = prepare_valid_ca(df_ca)
except Exception: traceback.print_exc()

try: valid_cp  = prepare_valid_cp(df_cp) if not df_cp.empty else pd.DataFrame()
except Exception: traceback.print_exc()

rdt_b_mq,  vol_b_mq  = _safe_brent(prices_mq,  valid_mq,  rallies)
rdt_b_act, vol_b_act = _safe_brent(prices_act, valid_act, rallies)
rdt_b_ca,  vol_b_ca  = _safe_brent(prices_ca,  valid_ca,  rallies)
rdt_b_cp,  vol_b_cp  = _safe_brent(prices_cp,  valid_cp,  rallies)

print(f"MQ : {len(valid_mq)} · ACT : {len(valid_act)} · "
      f"CA : {len(valid_ca)} · CP : {len(valid_cp)} · "
      f"Rallies : {len(rallies)}")
print("Cache Brent OK")

# ══════════════════════════════════════════════════════════════════════════════
# COLONNES DYNAMIQUES
# ══════════════════════════════════════════════════════════════════════════════
col_score_act   = 'Score global - Performance Score /100'
col_secteur_act = 'Secteur'
col_narr_act    = 'Score global - Narrative Score'
col_trend_act   = 'Score global - Trend Score'

col_score_ca    = 'Score_global_Cca'
col_secteur_ca  = 'Macro_Secteur'
col_quintile_ca = 'Quintile_ca'
col_pct_ca      = 'ca_percentile'

col_score_cp    = 'score'             
col_quintile_cp = 'Quintile_CP'      
col_pct_cp      = 'score_percentile'  
col_secteur_cp  = 'macro_sector' 


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
# HELPERS DATASET
# ══════════════════════════════════════════════════════════════════════════════
def _resolve_dataset(dataset):
    """Retourne (valid, prices, score_col, secteur_col, quintile_col, pct_col,
                  dataset_label, badge_class, company_col, is_mq, is_act, is_ca, is_cp)"""
    dataset = dataset or 'mq'
    is_mq  = dataset == 'mq'
    is_act = dataset == 'act'
    is_ca  = dataset == 'ca'
    is_cp  = dataset == 'cp'

    if is_mq:
        return dict(
            valid=valid_mq, prices=prices_mq,
            score_col='Score_global_MQ', secteur_col='Macro_Secteur',
            quintile_col='Quintile_MQ', pct_col='MQ_percentile',
            dataset_label='Management Quality', badge_class='dataset-badge-mq',
            company_col='Company Name',
            is_mq=True, is_act=False, is_ca=False, is_cp=False,
        )
    elif is_act:
        return dict(
            valid=valid_act, prices=prices_act,
            score_col=col_score_act, secteur_col=col_secteur_act,
            quintile_col='Quintile_ACT', pct_col='Score_percentile',
            dataset_label='ACT — Transition Carbone', badge_class='dataset-badge-act',
            company_col='Entreprise',
            is_mq=False, is_act=True, is_ca=False, is_cp=False,
        )
    elif is_ca:
        return dict(
            valid=valid_ca, prices=prices_ca,
            score_col=col_score_ca, secteur_col=col_secteur_ca,
            quintile_col=col_quintile_ca, pct_col=col_pct_ca,
            dataset_label='CA — Climate Action', badge_class='dataset-badge-ca',
            company_col='Company name',
            is_mq=False, is_act=False, is_ca=True, is_cp=False,
        )
    else:  # cp
        return dict(
            valid=valid_cp, prices=prices_cp if prices_cp is not None else pd.DataFrame(),
            score_col=col_score_cp, secteur_col=col_secteur_cp,
            quintile_col=col_quintile_cp, pct_col=col_pct_cp,
            dataset_label='CP — Carbon Performance', badge_class='dataset-badge-cp',
            company_col='Company Name',
            is_mq=False, is_act=False, is_ca=False, is_cp=True,
        )


# ══════════════════════════════════════════════════════════════════════════════
# COMPOSANTS STATIQUES (sidebar / topbar)
# ══════════════════════════════════════════════════════════════════════════════
NAV_ITEMS = [
    ('Accueil',           '/accueil',     ''),
    ('Société',           '/societe',     str(len(valid_mq))),
    ('Panel Quintiles',   '/panel',       ''),
    ('Analyse Brent',     '/brent',       ''),
    ('Régression OLS',    '/ols',         ''),
    ('Narrative / Trend', '/strategique', ''),
    ('Score Composite',   '/composite',   ''),
]


def _make_sidebar(username='', role='', display=''):
    """Sidebar statique — ne change qu'à la connexion."""
    initials = ''.join([p[0].upper() for p in display.split()[:2]]) if display else 'DC'
    is_admin = (role == 'Admin')

    nav_links = []
    for label, href, badge in NAV_ITEMS:
        nav_links.append(
            dcc.Link(
                href=href,
                className='nav-item',
                children=[
                    html.Span(label, className='nav-label'),
                    html.Span(badge, className='nav-badge') if badge else None,
                ],
            )
        )

    if is_admin:
        nav_links.append(
            dcc.Link(
                href='/admin',
                className='nav-item nav-item-admin',
                children=[html.Span('⚙ Administration', className='nav-label')],
            )
        )

    return html.Div(className='sidebar', children=[
        html.Div(className='sidebar-header', children=[
            html.Div(className='logo-row', children=[
                html.Div('T', className='logo-mark'),
                html.Div([
                    html.Div('DEFIS · Finance', className='logo-text'),
                    html.Div('Analyse 2025',    className='logo-sub'),
                ]),
            ]),
        ]),

        html.Div('Référentiel', className='ds-section'),
        html.Div(className='ds-toggle', children=[
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
            ),
        ]),

        html.Div('Vues', className='nav-section-label'),
        *nav_links,

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


# ══════════════════════════════════════════════════════════════════════════════
# LAYOUT PRINCIPAL — shell fixe + zone dynamique
# ══════════════════════════════════════════════════════════════════════════════
app.layout = html.Div([
    dcc.Location(id='url', refresh=False),

    # Store persistant pour le dataset choisi
    dcc.Store(id='store-dataset', data='mq', storage_type='local'),

    # Shell complet : sidebar (fixe) + colonne droite
    html.Div(
        id='app-shell',
        className='app-shell',
        children=[
            # ── Sidebar : rendue une seule fois, mise à jour uniquement si besoin ──
            html.Div(id='sidebar-container'),

            # ── Colonne principale ────────────────────────────────────────────────
            html.Div(className='main-content', children=[

                # Topbar dynamique (breadcrumb + badge dataset)
                html.Div(className='topbar', children=[
                    html.Div(className='breadcrumb', children=[
                        html.Span('Benchmark',            className='breadcrumb-root'),
                        html.Span('/',                    className='breadcrumb-sep'),
                        html.Span(id='breadcrumb-dataset'),
                        html.Span('/',                    className='breadcrumb-sep'),
                        html.Span(id='breadcrumb-page',   className='breadcrumb-active'),
                    ]),
                    html.Div(className='topbar-actions', children=[
                        html.Span(id='dataset-badge'),
                    ]),
                ]),

                # Zone de contenu — seul endroit qui change à chaque navigation
                html.Div(
                    id='page-content',
                    className='page-content',
                ),
            ]),
        ],
    ),
])


# ══════════════════════════════════════════════════════════════════════════════
# CALLBACKS
# ══════════════════════════════════════════════════════════════════════════════

# ── 1. Store dataset ← radio (persistance) ───────────────────────────────────
@app.callback(
    Output('store-dataset', 'data'),
    Input('radio-dataset', 'value'),
    prevent_initial_call=True,
)
def sync_store_from_radio(value):
    return value


# ── 2. Radio ← store (restore au chargement) ─────────────────────────────────
@app.callback(
    Output('radio-dataset', 'value'),
    Input('store-dataset', 'data'),
    prevent_initial_call=True,
)
def sync_radio_from_store(stored):
    return stored or 'mq'


# ── 3. Sidebar — rendue une seule fois par session (dépend de l'auth) ─────────
@app.callback(
    Output('sidebar-container', 'children'),
    Input('url', 'pathname'),   # déclenché au premier chargement uniquement
)
def render_sidebar(pathname):
    if current_user.is_authenticated:
        return _make_sidebar(
            username=current_user.id,
            role=current_user.role,
            display=current_user.display,
        )
    return _make_sidebar()


# ── 4. Topbar — mise à jour légère (textes seulement) ────────────────────────
@app.callback(
    Output('breadcrumb-dataset', 'children'),
    Output('breadcrumb-page',    'children'),
    Output('dataset-badge',      'children'),
    Output('dataset-badge',      'className'),
    Input('url',          'pathname'),
    Input('store-dataset', 'data'),
)
def update_topbar(pathname, dataset):
    ds      = _resolve_dataset(dataset)
    label   = ds['dataset_label']
    badge   = ds['badge_class']

    page_map = {
        '/accueil':     'Accueil',
        '/societe':     'Société',
        '/panel':       'Panel Quintiles',
        '/brent':       'Analyse Brent',
        '/ols':         'Régression OLS',
        '/strategique': 'Narrative / Trend',
        '/composite':   'Score Composite',
        '/admin':       'Administration',
    }
    page_name = page_map.get(pathname or '/accueil', 'Accueil')

    return label, page_name, label, badge


# ── 5. Contenu de page — seul callback "lourd" ───────────────────────────────
@app.callback(
    Output('page-content', 'children'),
    Input('url',           'pathname'),
    Input('store-dataset', 'data'),
)
def render_page(pathname, dataset):
    if not pathname or pathname in ('/', '/login'):
        pathname = '/accueil'

    # Garde admin
    if pathname == '/admin':
        if not current_user.is_authenticated or current_user.role != 'Admin':
            return html.Div(
                html.Div("⛔ Accès réservé à l'administrateur.", className='warn-box'),
                style={'padding': '40px'},
            )

    ds  = _resolve_dataset(dataset)
    ctx = {**APP_DATA, **ds}

    layout_map = {
        '/accueil':     layout_accueil,
        '/societe':     layout_societe,
        '/panel':       layout_panel,
        '/brent':       layout_brent,
        '/ols':         layout_ols,
        '/strategique': layout_strategique,
        '/composite':   layout_composite,
        '/admin':       layout_admin,
    }

    layout_fn = layout_map.get(pathname, layout_accueil)

    # dcc.Loading uniquement autour du contenu, pas du shell entier
    return dcc.Loading(
        type='circle',
        color='#1f6feb',
        children=layout_fn(ctx),
    )


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
