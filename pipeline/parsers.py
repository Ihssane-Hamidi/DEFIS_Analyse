"""
pipeline/parsers.py
Un parser par format xlsx : MQ / ACT / CA / CP.
Chaque fonction retourne (df_scores, company_col, isin_col, score_col, quintile_col)
"""

import io
import numpy as np
import pandas as pd
from .common import MACRO_SECTEUR


# ══════════════════════════════════════════════════════════════════════════════
# SCHÉMAS DE VALIDATION PAR FORMAT
# ══════════════════════════════════════════════════════════════════════════════

REQUIRED_COLS = {
    'mq':  ['Company Name', 'Sector', 'Level', 'Publication Date'],
    'act': ['Entreprise', 'ISIN', 'Secteur', 'Score global - Performance Score /100'],
    'ca':  ['Company name', 'Sector', 'ISIN'],
    'cp':  ['Company Name', 'ISIN', 'Sector'],
}

MQ_EDITION_DEFAULT = '15/12/2025'


# ══════════════════════════════════════════════════════════════════════════════
# PARSER MQ (TPI Management Quality)
# ══════════════════════════════════════════════════════════════════════════════

def parse_mq(
    file_bytes: bytes,
    edition_date: str = MQ_EDITION_DEFAULT,
    sheet_name: str = 'Feuille 1 - MQ_Assessments_v5_1',
) -> tuple[pd.DataFrame, str, str, str, str]:
    """
    Parse le fichier MQ TPI.
    Retourne (df, company_col, isin_col, score_col, quintile_col)
    """
    df_raw = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet_name, header=None)
    df     = df_raw.iloc[2:].copy()
    df.columns = df_raw.iloc[1].values
    df     = df.reset_index(drop=True)

    # Filtre sur la date d'édition
    df25 = df[df['Publication Date'] == edition_date].copy().reset_index(drop=True)
    if df25.empty:
        # Fallback : prendre la date la plus récente disponible
        df25 = df[df['Publication Date'] == df['Publication Date'].max()].copy().reset_index(drop=True)

    _validate(df25, 'mq')

    # Nettoyage Level
    def parse_level(v):
        if pd.isna(v): return np.nan
        v = str(v).strip()
        if v in ('5STAR', '5'): return 5
        try: return float(v)
        except: return np.nan

    df25['Level_num'] = df25['Level'].apply(parse_level)

    # Score MQ : moyenne des questions Q*|*
    q_cols = [c for c in df25.columns if str(c).startswith('Q') and '|' in str(c)]

    def map_mq(val):
        if pd.isna(val): return np.nan
        v = str(val).strip()
        if v == 'Yes':                                return 1.0
        if v in ('No', 'No Data'):                    return 0.0
        if v in ('Not Applicable', 'Not applicable'): return np.nan
        return np.nan

    for c in q_cols:
        df25[c] = df25[c].apply(map_mq)

    level_map = {
        'L0': ['Q1L0'], 'L1': ['Q2L1','Q3L1'], 'L2': ['Q4L2','Q5L2'],
        'L3': ['Q6L3','Q7L3','Q8L3','Q9L3','Q10L3','Q11L3','Q12L3'],
        'L4': ['Q13L4','Q14L4','Q15L4','Q16L4','Q17L4','Q18L4'],
        'L5': ['Q19L5','Q20L5','Q21L5','Q22L5','Q23L5'],
    }

    def find_col(qcode):
        for c in q_cols:
            if c.startswith(qcode + '|'): return c
        return None

    for lvl, qs in level_map.items():
        cols = [find_col(q) for q in qs if find_col(q)]
        df25[f'rate_{lvl}'] = df25[cols].mean(axis=1)

    df25['Score_global_MQ'] = df25[q_cols].mean(axis=1)
    df25['MQ_percentile']   = df25['Score_global_MQ'].rank(pct=True)
    df25['Macro_Secteur']   = df25['Sector'].map(MACRO_SECTEUR).fillna('Other')

    # Colonnes ISIN : 'ISINs' dans MQ
    isin_col = 'ISINs' if 'ISINs' in df25.columns else 'ISIN'

    return df25, 'Company Name', isin_col, 'Score_global_MQ', 'Quintile_MQ'


# ══════════════════════════════════════════════════════════════════════════════
# PARSER ACT
# ══════════════════════════════════════════════════════════════════════════════

def parse_act(file_bytes: bytes) -> tuple[pd.DataFrame, str, str, str, str]:
    """
    Parse le fichier ACT.
    Colonnes clés : Entreprise, ISIN, Secteur, Score global - Performance Score /100
    """
    df = pd.read_excel(io.BytesIO(file_bytes))
    _validate(df, 'act')

    score_col = 'Score global - Performance Score /100'
    df[score_col] = pd.to_numeric(df[score_col], errors='coerce')

    # Sous-scores détail
    detail_cols = [c for c in df.columns if c.startswith('Détail -')]
    for c in detail_cols:
        df[c] = pd.to_numeric(df[c], errors='coerce')

    # Secteur → Macro_Secteur (colonne 'Secteur' en français)
    sector_col = 'Secteur' if 'Secteur' in df.columns else None
    if sector_col:
        df['Macro_Secteur'] = df[sector_col].map(MACRO_SECTEUR).fillna('Other')

    df['ACT_percentile'] = df[score_col].rank(pct=True)

    return df, 'Entreprise', 'ISIN', score_col, 'Quintile_ACT'


# ══════════════════════════════════════════════════════════════════════════════
# PARSER CA (Climate Action 100+)
# ══════════════════════════════════════════════════════════════════════════════

def parse_ca(
    file_bytes: bytes,
    sheet_name: str = 'Disclosure Assessments (TPI)',
) -> tuple[pd.DataFrame, str, str, str, str]:
    """
    Parse le fichier CA avec header multi-lignes (lignes 8,9,10).
    """
    df_raw = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet_name, header=None)

    # Reconstruction header
    row8  = df_raw.iloc[8].ffill()
    row9  = df_raw.iloc[9]
    row10 = df_raw.iloc[10]
    col_names  = []
    seen_names = {}

    for i in range(df_raw.shape[1]):
        r8  = str(row8.iloc[i]).strip()  if pd.notna(row8.iloc[i])  else ''
        r9  = str(row9.iloc[i]).strip()  if pd.notna(row9.iloc[i])  else ''
        r10 = str(row10.iloc[i]).strip() if pd.notna(row10.iloc[i]) else ''

        if 'Progress' in r10:
            col_names.append('__SKIP__')
            continue

        if r9 and not r9.startswith('Please see') and 'Unnamed' not in r9:
            name = r9
        elif r8 and 'Unnamed' not in r8:
            name = r8
        else:
            name = f'col_{i}'

        if name in seen_names:
            seen_names[name] += 1
            name = f'{name}_{seen_names[name]}'
        else:
            seen_names[name] = 1
        col_names.append(name)

    df_ca = df_raw.iloc[11:].copy()
    df_ca.columns = col_names
    df_ca = df_ca[[c for c in df_ca.columns if c != '__SKIP__']].reset_index(drop=True)
    df_ca = df_ca.dropna(how='all').reset_index(drop=True)
    df_ca = df_ca[df_ca['Company name'].notna()].reset_index(drop=True)

    _validate(df_ca, 'ca')

    # Score CA : Yes=1 / Partial=0.5 / No=0
    ca_cols = [c for c in df_ca.columns if 'Sub-indicator' in c]

    def map_ca(val):
        if pd.isna(val): return np.nan
        v = str(val).strip().lower()
        if v == 'yes':               return 1.0
        if v == 'partial':           return 0.5
        if v in ('no', 'no data'):   return 0.0
        return np.nan

    for c in ca_cols:
        df_ca[f'val_{c}'] = df_ca[c].apply(map_ca)

    val_cols = [f'val_{c}' for c in ca_cols]
    df_ca['Score_global_CA'] = df_ca[val_cols].mean(axis=1)
    df_ca['CA_percentile']   = df_ca['Score_global_CA'].rank(pct=True)
    df_ca['Macro_Secteur']   = df_ca['Sector'].map(MACRO_SECTEUR).fillna('Other')

    return df_ca, 'Company name', 'ISIN', 'Score_global_CA', 'Quintile_CA'


# ══════════════════════════════════════════════════════════════════════════════
# PARSER CP (Carbon Performance)
# ══════════════════════════════════════════════════════════════════════════════

# Ordre des alignements du meilleur au moins bon
CP_ALIGNMENT_ORDER = {
    '1.5°C Aligned':        5,
    'Below 2°C':            4,
    '2°C Aligned':          3,
    'International Pledges': 2,
    'Not Aligned':           1,
}

def parse_cp(
    file_bytes: bytes,
    alignment_cols: list[str] | None = None,
) -> tuple[pd.DataFrame, str, str, str, str]:
    """
    Parse le fichier Carbon Performance (CP).
    Les colonnes L→P contiennent les alignements climatiques par année.
    Score CP = moyenne des valeurs numériques d'alignement.
    """
    df = pd.read_excel(io.BytesIO(file_bytes))
    _validate(df, 'cp')

    # Détection automatique des colonnes d'alignement (L→P = colonnes 11→15)
    if alignment_cols is None:
        # Cherche les colonnes qui contiennent des valeurs d'alignement connus
        alignment_cols = [
            c for c in df.columns
            if df[c].dropna().astype(str).str.strip().isin(CP_ALIGNMENT_ORDER.keys()).any()
        ]
        if not alignment_cols:
            # Fallback : colonnes L à P par position (index 11 à 15)
            all_cols = list(df.columns)
            alignment_cols = all_cols[11:16] if len(all_cols) >= 16 else all_cols[11:]

    # Conversion alignement → score numérique
    def map_cp(val):
        if pd.isna(val): return np.nan
        v = str(val).strip()
        return CP_ALIGNMENT_ORDER.get(v, np.nan)

    for c in alignment_cols:
        df[f'cp_score_{c}'] = df[c].apply(map_cp)

    cp_score_cols = [f'cp_score_{c}' for c in alignment_cols]
    df['Score_global_CP'] = df[cp_score_cols].mean(axis=1)

    # Alignement le plus récent (dernière colonne non nulle)
    def best_alignment(row):
        for c in reversed(alignment_cols):
            v = str(row.get(c, '')).strip()
            if v in CP_ALIGNMENT_ORDER:
                return v
        return 'Not Aligned'

    df['CP_alignment_latest'] = df.apply(best_alignment, axis=1)
    df['CP_percentile']       = df['Score_global_CP'].rank(pct=True)

    if 'Sector' in df.columns:
        df['Macro_Secteur'] = df['Sector'].map(MACRO_SECTEUR).fillna('Other')

    return df, 'Company Name', 'ISIN', 'Score_global_CP', 'Quintile_CP'


# ══════════════════════════════════════════════════════════════════════════════
# UTILITAIRES
# ══════════════════════════════════════════════════════════════════════════════

def _validate(df: pd.DataFrame, fmt: str):
    """Vérifie que les colonnes obligatoires sont présentes."""
    missing = [c for c in REQUIRED_COLS[fmt] if c not in df.columns]
    if missing:
        raise ValueError(
            f"[Parser {fmt.upper()}] Colonnes manquantes : {missing}\n"
            f"Colonnes trouvées : {list(df.columns[:20])}"
        )


def get_parser(dataset_type: str):
    """Retourne la fonction parser correspondant au type de dataset."""
    parsers = {
        'mq': parse_mq,
        'act': parse_act,
        'ca': parse_ca,
        'cp': parse_cp,
    }
    if dataset_type not in parsers:
        raise ValueError(f"Type inconnu : {dataset_type}. Valeurs valides : {list(parsers)}")
    return parsers[dataset_type]
