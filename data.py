#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
data.py — Chargement et constantes
TPI · Analyse Financière (Dash)
"""

import os
import io
import pandas as pd
from functools import lru_cache
from pipeline.drive import load_parquet

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

# ── CHEMINS LOCAL (dev Mac uniquement) ────────────────────────────────────────
LOCAL_DIR = '/Users/hamidi/Desktop/tpi_dash'

LOCAL_FILES = {
    'mq':      'mq_metriques.parquet',
    'mq_prix': 'mq_prix_journaliers.parquet',
    'act':     'act_metriques.parquet',
    'act_prix':'act_prix_journaliers.parquet',
    'ca':      'ca_metriques.parquet',
    'ca_prix': 'ca_prix_journaliers.parquet',
    'cp':      'cp_metriques.parquet',
    'cp_prix': 'cp_prix_journaliers.parquet',
    'brent':   'brent.parquet',
}


# ══════════════════════════════════════════════════════════════════════════════
# CHARGEMENT UNIFIÉ : Local (dev) → Drive (prod)
# ══════════════════════════════════════════════════════════════════════════════

def _load_df(key: str, is_prix: bool = False) -> pd.DataFrame | None:
    """
    Charge un parquet :
    - dev  : depuis LOCAL_DIR si le fichier existe
    - prod : depuis Google Drive via pipeline.drive
    Retourne None si non trouvé (dataset pas encore généré).
    """
    # ── Dev local ─────────────────────────────────────────────────────────
    filename = LOCAL_FILES.get(key)
    if filename:
        local_path = os.path.join(LOCAL_DIR, filename)
        if os.path.exists(local_path):
            df = pd.read_parquet(local_path)
            if is_prix:
                df.index = pd.to_datetime(df.index)
            return df

    # ── Prod : Google Drive ───────────────────────────────────────────────
    try:
        from pipeline.drive import load_parquet
        df = load_parquet(key)
        if df is not None and is_prix:
            df.index = pd.to_datetime(df.index)
        return df
    except Exception as e:
        print(f"[data._load_df] Erreur chargement '{key}' depuis Drive : {e}")
        return None


# ── LOADERS PAR DATASET ───────────────────────────────────────────────────────
# Note : pas de @lru_cache ici pour permettre le hot-reload
#         admin uploade un nouveau parquet.
#        Le cache est géré au niveau de APP_DATA dans app.py.

def load_mq():       return _load_df('mq')
def load_mq_prix():  return _load_df('mq_prix',  is_prix=True)
def load_act():      return _load_df('act')
def load_act_prix(): return _load_df('act_prix', is_prix=True)
def load_ca():       return _load_df('ca')
def load_ca_prix():  return _load_df('ca_prix',  is_prix=True)
def load_cp():       return _load_df('cp')
def load_cp_prix():  return _load_df('cp_prix',  is_prix=True)


def load_brent() -> pd.Series:
    """Charge le Brent. Fallback yfinance si introuvable."""
    # Dev local
    local_path = os.path.join(LOCAL_DIR, 'brent.parquet')
    if os.path.exists(local_path):
        return pd.read_parquet(local_path)['Close']

    # Drive
    try:
        from pipeline.drive import load_parquet
        df = load_parquet('brent.parquet')
        if df is not None:
            return df['Close']
    except Exception:
        pass

    # Fallback live yfinance
    try:
        import yfinance as yf
        print("Brent non trouvé → téléchargement live yfinance...")
        df = yf.download('BZ=F', start='2022-01-01', auto_adjust=True, progress=False)
        return df['Close']
    except Exception as e:
        print(f"[load_brent] Erreur fallback yfinance : {e}")
        return pd.Series(dtype=float)


# ══════════════════════════════════════════════════════════════════════════════
# PRÉPARATION DES DATAFRAMES VALIDES
# ══════════════════════════════════════════════════════════════════════════════

def _prepare_valid(df: pd.DataFrame, company_col: str) -> pd.DataFrame:
    """
    Filtre les entreprises avec ticker + données financières.
    Normalise le nom de la colonne entreprise en 'Company Name'.
    Détecte dynamiquement la colonne de rendement long terme disponible.
    """
    if df is None:
        return pd.DataFrame()

    # Colonne rendement long terme (flexible selon les années uploadées)
    rdt_cols = [c for c in df.columns if c.startswith('Rendement_') and '_' in c.replace('Rendement_', '')]
    rdt_col  = rdt_cols[-1] if rdt_cols else None  # prend le plus long par ordre alpha

    mask = df['ticker'].notna() & (df['ticker'].astype(str) != 'None')
    if rdt_col:
        mask = mask & df[rdt_col].notna()

    valid = df[mask].copy()

    if company_col in valid.columns and company_col != 'Company Name':
        valid = valid.rename(columns={company_col: 'Company Name'})

    return valid


def prepare_valid_mq(df_mq):
    return _prepare_valid(df_mq, 'Company Name')

def prepare_valid_act(df_act):
    return _prepare_valid(df_act, 'Entreprise')

def prepare_valid_ca(df_ca):
    return _prepare_valid(df_ca, 'Company name')

def prepare_valid_cp(df_cp):
    return _prepare_valid(df_cp, 'Company Name')
