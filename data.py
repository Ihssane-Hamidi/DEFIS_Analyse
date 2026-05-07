#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Apr 27 00:41:37 2026

@author: hamidi
"""


"""
data.py — Chargement et constantes
TPI · Analyse Financière (Dash)
"""

import os
import requests
import pandas as pd
from functools import lru_cache


#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
data.py — Chargement et constantes
TPI · Analyse Financière (Dash)
"""

import os
import requests
import pandas as pd
from functools import lru_cache


# ── CHEMINS ───────────────────────────────────────────────────────────────────
BASE_DIR           = os.path.dirname(os.path.abspath(__file__))
LOCAL_DIR          = '/Users/hamidi/Desktop/tpi_dash'
GITHUB_RELEASE_URL = "https://github.com/Ihssane-Hamidi/DEFIS_Analyse/releases/download/v1.0/"
FILES = {
    'mq_metriques':  'mq_metriques.parquet',
    'mq_prix':       'mq_prix_journaliers.parquet',
    'act_metriques': 'act_metriques.parquet',
    'act_prix':      'act_prix_journaliers.parquet',
    'ca_metriques':  'CA_metriques.parquet',
    'ca_prix':       'CA_prix_journaliers.parquet',
    'cp_metriques':  'cp_metriques.parquet',
    'cp_prix':       'cp_prix_journaliers.parquet',
}

# ── CONSTANTES ────────────────────────────────────────────────────────────────
PERIODS_LABELS = {
    '2023':      '2023',
    '2024':      '2024',
    '2025':      '2025',
    '2023_2025': '2023–2025',
}

QUINTILE_COLORS = {
    'Q1': '#ef4444',
    'Q2': '#f97316',
    'Q3': '#a3a3a3',
    'Q4': '#86efac',
    'Q5': '#16a34a',
}

PLOTLY_LAYOUT = dict(
    template='plotly_dark',
    paper_bgcolor='rgba(0,0,0,0)',
    plot_bgcolor='rgba(0,0,0,0)',
    margin=dict(l=0, r=0, t=30, b=0),
)


# ── TÉLÉCHARGEMENT ────────────────────────────────────────────────────────────
def get_parquet(key):
    filename = FILES[key]

    local = os.path.join(LOCAL_DIR, filename)
    if os.path.exists(local):
        return local

    project_data = os.path.join(BASE_DIR, 'data', filename)
    if os.path.exists(project_data):
        return project_data

    tmp_path = os.path.join('/tmp', filename)
    if os.path.exists(tmp_path):
        return tmp_path

    url = GITHUB_RELEASE_URL + filename
    print(f"Téléchargement {filename}...")
    r = requests.get(url, stream=True, timeout=120)
    r.raise_for_status()
    with open(tmp_path, 'wb') as f:
        for chunk in r.iter_content(chunk_size=65536):
            f.write(chunk)
    return tmp_path


# ── CHARGEMENT (mis en cache) ─────────────────────────────────────────────────
@lru_cache(maxsize=None)
def load_mq():
    return pd.read_parquet(get_parquet('mq_metriques'))

@lru_cache(maxsize=None)
def load_mq_prix():
    df = pd.read_parquet(get_parquet('mq_prix'))
    df.index = pd.to_datetime(df.index)
    return df

@lru_cache(maxsize=None)
def load_act():
    return pd.read_parquet(get_parquet('act_metriques'))

@lru_cache(maxsize=None)
def load_act_prix():
    df = pd.read_parquet(get_parquet('act_prix'))
    df.index = pd.to_datetime(df.index)
    return df

@lru_cache(maxsize=None)
def load_ca():
    return pd.read_parquet(get_parquet('ca_metriques'))

@lru_cache(maxsize=None)
def load_ca_prix():
    df = pd.read_parquet(get_parquet('ca_prix'))
    df.index = pd.to_datetime(df.index)
    return df

@lru_cache(maxsize=None)
def load_cp():
    return pd.read_parquet(get_parquet('cp_metriques'))

@lru_cache(maxsize=None)
def load_cp_prix():
    df = pd.read_parquet(get_parquet('cp_prix'))
    df.index = pd.to_datetime(df.index)
    return df

@lru_cache(maxsize=None)
def load_brent():
    filename = 'brent.parquet'

    for path in [
        os.path.join(LOCAL_DIR,   filename),
        os.path.join(BASE_DIR, 'data', filename),
        os.path.join(BASE_DIR,    filename),
    ]:
        if os.path.exists(path):
            return pd.read_parquet(path)['Close']

    try:
        url = GITHUB_RELEASE_URL + filename
        print(f"Téléchargement {filename} depuis GitHub...")
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        tmp_path = os.path.join('/tmp', filename)
        with open(tmp_path, 'wb') as f:
            f.write(r.content)
        return pd.read_parquet(tmp_path)['Close']
    except Exception as e:
        print(f"ERREUR brent : {e}")
        return pd.Series(dtype=float)


# ── HELPERS QUINTILES ─────────────────────────────────────────────────────────
def _add_quintiles(valid, score_col, quintile_col, pct_col):
    """
    Ajoute quintile_col et pct_col si absents.
    Utilise rank(method='first') pour éviter les ties dans qcut.
    """
    if pct_col not in valid.columns:
        valid[pct_col] = valid[score_col].rank(pct=True)

    if quintile_col not in valid.columns:
        try:
            valid[quintile_col] = pd.qcut(
                valid[score_col].rank(method='first'),
                q=5,
                labels=['Q1', 'Q2', 'Q3', 'Q4', 'Q5'],
            )
        except Exception as e:
            print(f"  ✗ qcut {quintile_col} : {e}")
            valid[quintile_col] = pd.NA

    return valid


# ── PRÉPARATION DES DATAFRAMES ────────────────────────────────────────────────
# NOTE : pas de @lru_cache ici — lru_cache ne supporte pas les DataFrames
#        (non hashables). Le cache est inutile car ces fonctions ne sont
#        appelées qu'une seule fois au démarrage dans app.py.

def prepare_valid_mq(df_mq):
    """Filtre MQ et s'assure que Quintile_MQ / MQ_percentile existent."""
    valid = df_mq[
        df_mq['ticker'].notna() &
        (df_mq['ticker'].astype(str) != 'None') &
        df_mq['Rendement_2023_2025'].notna()
    ].copy()

    if 'Company Name' not in valid.columns:
        valid = valid.rename(columns={valid.columns[0]: 'Company Name'})

    valid = _add_quintiles(valid, 'Score_global_MQ', 'Quintile_MQ', 'MQ_percentile')
    return valid


def prepare_valid_act(df_act):
    """Filtre ACT et s'assure que Quintile_ACT / Score_percentile existent."""
    col_nom = df_act.columns[0]
    valid = df_act[
        df_act['ticker'].notna() &
        (df_act['ticker'].astype(str) != 'None') &
        df_act['Rendement_2023_2025'].notna()
    ].copy()
    valid = valid.rename(columns={col_nom: 'Company Name'})

    score_col = 'Score global - Performance Score /100'
    valid = _add_quintiles(valid, score_col, 'Quintile_ACT', 'Score_percentile')
    return valid


def prepare_valid_ca(df_ca):
    """Filtre CA et s'assure que Quintile_ca / ca_percentile existent."""
    df_ca = df_ca.loc[:, ~df_ca.columns.duplicated()]
    col_nom = df_ca.columns[0]

    valid = df_ca[
        df_ca['ticker'].notna() &
        (df_ca['ticker'].astype(str) != 'None') &
        df_ca['Rendement_2023_2025'].notna()
    ].copy()

    if col_nom != 'Company name':
        valid = valid.rename(columns={col_nom: 'Company name'})

    valid = _add_quintiles(valid, 'Score_global_Cca', 'Quintile_ca', 'ca_percentile')
    return valid


def prepare_valid_cp(df_cp):
    """Filtre CP et s'assure que Quintile_CP / score_percentile existent."""
    df_cp = df_cp.loc[:, ~df_cp.columns.duplicated()]
    col_nom = df_cp.columns[0]

    valid = df_cp[
        df_cp['ticker'].notna() &
        (df_cp['ticker'].astype(str) != 'None') &
        df_cp['Rendement_2023_2025'].notna()
    ].copy()

    if col_nom != 'Company Name':
        valid = valid.rename(columns={col_nom: 'Company Name'})

    valid = _add_quintiles(valid, 'score', 'Quintile_CP', 'score_percentile')
    return valid
