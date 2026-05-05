"""
pipeline/builder.py
Orchestre le pipeline complet pour n'importe quel format (MQ/ACT/CA/CP).
Appelé depuis la page admin Dash.
"""

import json
import tempfile
import os
import pandas as pd

from .common import (
    build_periods,
    resolve_tickers_parallel,
    download_prices,
    fetch_all_fundamentals,
    compute_financial_metrics,
    add_quintiles,
    clean_for_parquet,
)
from .parsers import get_parser
from .drive import save_parquet


# ══════════════════════════════════════════════════════════════════════════════
# COLONNES À CONSERVER PAR FORMAT (scores + identifiants)
# ══════════════════════════════════════════════════════════════════════════════

COLS_TO_KEEP = {
    'mq': [
        'Company Name', 'ISINs', 'Sector', 'Macro_Secteur', 'Geography',
        'Level', 'Level_num', 'Score_global_MQ', 'MQ_percentile',
        'rate_L0', 'rate_L1', 'rate_L2', 'rate_L3', 'rate_L4', 'rate_L5',
    ],
    'act': [
        'Entreprise', 'ISIN', 'LEI', 'SIREN', 'Secteur', 'Macro_Secteur',
        'Méthodologie d\'évaluation ACT', 'Sous-type', 'Année de référence',
        'Score global - Performance Score /100',
        'Score global - Narrative Score', 'Score global - Trend Score',
        'ACT_percentile',
        'Détail - 1 Targets Score', 'Détail - 2 Material Investment Score',
        'Détail - 3 Intangible Investment Score',
        'Détail - 4 Sold Product Performance Score',
        'Détail - 5 Management Score', 'Détail - 6 Supplier Engagement Score',
        'Détail - 7 Client Engagement Score', 'Détail - 8 Client Engagement Score',
        'Détail - 9 BusinessModelScore',
    ],
    'ca': [
        'Company name', 'ISIN', 'Sector', 'Macro_Secteur', 'Geography',
        'Score_global_CA', 'CA_percentile',
    ],
    'cp': [
        'Company Name', 'ISIN', 'Sector', 'Macro_Secteur',
        'Score_global_CP', 'CP_percentile', 'CP_alignment_latest',
    ],
}

# Mapping company_col par format (pour les merges)
COMPANY_COL = {
    'mq':  'Company Name',
    'act': 'Entreprise',
    'ca':  'Company name',
    'cp':  'Company Name',
}

ISIN_COL = {
    'mq':  'ISINs',
    'act': 'ISIN',
    'ca':  'ISIN',
    'cp':  'ISIN',
}


# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

def run_pipeline(
    file_bytes: bytes,
    dataset_type: str,        # 'mq' | 'act' | 'ca' | 'cp'
    years: list[int],         # ex: [2023, 2024, 2025]
    ticker_cache: dict,       # cache partagé ISIN→ticker
    progress_cb=None,         # callable(étape: str, done: int, total: int)
    save_to_drive: bool = True,
) -> dict:
    """
    Pipeline complet : parse → tickers → prix → métriques → parquet → Drive.

    Retourne un dict de résultat :
    {
        'success': bool,
        'df_metriques': pd.DataFrame,
        'df_prix': pd.DataFrame,
        'n_total': int,
        'n_tickers': int,
        'n_fin': int,
        'error': str | None,
    }
    """
    result = {
        'success': False,
        'df_metriques': None,
        'df_prix': None,
        'n_total': 0,
        'n_tickers': 0,
        'n_fin': 0,
        'error': None,
    }

    def _progress(step, done=0, total=0):
        if progress_cb:
            progress_cb(step, done, total)

    try:
        # ── 1. Parse xlsx ────────────────────────────────────────────────────
        _progress('parse')
        parser = get_parser(dataset_type)
        df_scores, company_col, isin_col, score_col, quintile_col = parser(file_bytes)

        n_total = len(df_scores)
        result['n_total'] = n_total
        _progress('parse', n_total, n_total)

        # ── 2. Résolution tickers ────────────────────────────────────────────
        _progress('tickers', 0, n_total)
        rows = [
            {
                'isin': str(r.get(isin_col, '')).strip() if pd.notna(r.get(isin_col)) else '',
                'name': str(r.get(company_col, '')).strip(),
            }
            for _, r in df_scores.iterrows()
        ]

        tickers = resolve_tickers_parallel(
            rows, ticker_cache,
            progress_cb=lambda done, total: _progress('tickers', done, total)
        )
        df_scores['ticker'] = tickers
        n_tickers = sum(1 for t in tickers if t)
        result['n_tickers'] = n_tickers
        _progress('tickers', n_total, n_total)

        # ── 3. Téléchargement prix ───────────────────────────────────────────
        periods    = build_periods(years)
        start_date = f'{min(years)}-01-01'
        end_date   = f'{max(years)}-12-31'
        valid_tickers = df_scores['ticker'].dropna().unique().tolist()
        valid_tickers = [t for t in valid_tickers if str(t) != 'None']

        _progress('prix', 0, len(valid_tickers))
        df_prix = download_prices(
            valid_tickers, start_date, end_date,
            progress_cb=lambda done, total: _progress('prix', done, total)
        )
        _progress('prix', len(valid_tickers), len(valid_tickers))

        # ── 4. Fondamentaux ──────────────────────────────────────────────────
        _progress('fondamentaux', 0, len(valid_tickers))
        df_fund = fetch_all_fundamentals(
            valid_tickers,
            progress_cb=lambda done, total: _progress('fondamentaux', done, total)
        )
        _progress('fondamentaux', len(valid_tickers), len(valid_tickers))

        # ── 5. Métriques financières ─────────────────────────────────────────
        _progress('métriques')
        df_fin = compute_financial_metrics(
            df_scores, df_prix, periods, company_col
        )
        df_fin = df_fin.drop_duplicates(subset=company_col, keep='first').reset_index(drop=True)

        # ── 6. Fusion ────────────────────────────────────────────────────────
        _progress('fusion')
        keep = [c for c in COLS_TO_KEEP[dataset_type] if c in df_scores.columns]
        # Ajoute val_* pour CA dynamiquement
        if dataset_type == 'ca':
            keep += [c for c in df_scores.columns if c.startswith('val_')]

        df_final = df_scores[keep].merge(df_fin, on=company_col, how='left')
        df_final = df_final.merge(
            df_fund[['ticker', 'MarketCap', 'LogMarketCap', 'BookToMarket']],
            on='ticker', how='left', validate='m:1'
        )

        # ── 7. Quintiles ─────────────────────────────────────────────────────
        mask = (
            df_final['ticker'].notna()
            & (df_final['ticker'].astype(str) != 'None')
        )
        # Filtre sur une colonne de rendement si disponible
        rdt_col = next(
            (c for c in df_final.columns if c.startswith('Rendement_') and '_' in c.replace('Rendement_','')),
            None
        )
        if rdt_col:
            mask = mask & df_final[rdt_col].notna()

        df_final = add_quintiles(df_final, score_col, quintile_col, mask)
        n_fin = int(df_final[rdt_col].notna().sum()) if rdt_col else 0
        result['n_fin'] = n_fin

        # ── 8. Nettoyage Parquet ─────────────────────────────────────────────
        df_final = clean_for_parquet(df_final)

        result['df_metriques'] = df_final
        result['df_prix']      = df_prix

        # ── 9. Sauvegarde Drive ──────────────────────────────────────────────
        if save_to_drive:
            _progress('drive')
            save_parquet(df_final, dataset_type)
            save_parquet(df_prix,  f'{dataset_type}_prix')

        result['success'] = True
        _progress('terminé', n_total, n_total)

    except Exception as e:
        import traceback
        result['error'] = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        _progress('erreur')

    return result
