"""
pipeline/common.py
Fonctions partagées pour tous les formats (MQ / ACT / CA / CP).
Résolution tickers, téléchargement prix, calcul métriques.
"""

import json
import time
import numpy as np
import pandas as pd
import yfinance as yf
from yahooquery import search as yq_search
from concurrent.futures import ThreadPoolExecutor, as_completed


# ══════════════════════════════════════════════════════════════════════════════
# MACRO-SECTEURS (partagé par tous les formats)
# ══════════════════════════════════════════════════════════════════════════════
MACRO_SECTEUR = {
    'Oil & Gas': 'Fossil Fuels', 'Coal Mining': 'Fossil Fuels',
    'Oil Refining and Marketing': 'Fossil Fuels', 'Oil Equipment and Services': 'Fossil Fuels',
    'Oil & Gas Distribution': 'Fossil Fuels', 'Offshore Drilling and Other Services': 'Fossil Fuels',
    'Electricity Utilities': 'Utilities', 'Multi-Utilities': 'Utilities',
    'Renewable Energy Equipment': 'Utilities', 'Alternative Fuels': 'Utilities',
    'General Industrials': 'Industrials', 'Industrial Engineering': 'Industrials',
    'Industrial Transportation': 'Industrials', 'Industrial Support Services': 'Industrials',
    'Aerospace and Defense': 'Industrials', 'Construction and Materials': 'Industrials',
    'Commercial Vehicles and Parts': 'Industrials', 'Industrial Materials': 'Industrials',
    'Waste & Disposal Services': 'Industrials', 'Shipping': 'Industrials', 'Airlines': 'Industrials',
    'Steel': 'Materials', 'Chemicals': 'Materials', 'Cement': 'Materials',
    'Aluminium': 'Materials', 'Copper': 'Materials', 'Nonferrous Metals': 'Materials',
    'Paper': 'Materials', 'Diversified Mining': 'Materials',
    'Precious Metals and Mining': 'Materials', 'Metal Fabricating': 'Materials',
    'Banks': 'Financials', 'Insurance': 'Financials',
    'Investment Banking and Brokerage Services': 'Financials',
    'Real Estate Investment Trusts': 'Financials',
    'Real Estate Investment and Services Development': 'Financials',
    'Finance and Credit Services': 'Financials',
    'Food Producers': 'Consumer', 'Beverages': 'Consumer', 'Retailers': 'Consumer',
    'Personal Care, Drug and Grocery Stores': 'Consumer', 'Personal Goods': 'Consumer',
    'Tobacco': 'Consumer', 'Leisure Goods': 'Consumer', 'Travel and Leisure': 'Consumer',
    'Household Goods and Home Construction': 'Consumer', 'Consumer Services': 'Consumer',
    'Technology Hardware & Equipment': 'Technology', 'Software & Computer Services': 'Technology',
    'Telecommunications Service Providers': 'Technology',
    'Electronic and Electrical Equipment': 'Technology', 'Telecommunications Equipment': 'Technology',
    'Pharmaceuticals and Biotechnology': 'Health & Other',
    'Medical Equipment and Services': 'Health & Other', 'Health Care Providers': 'Health & Other',
    'Autos': 'Health & Other', 'Auto Services and Parts': 'Health & Other', 'Media': 'Health & Other',
}

# ══════════════════════════════════════════════════════════════════════════════
# RÉSOLUTION TICKERS
# ══════════════════════════════════════════════════════════════════════════════

def get_ticker(isin: str, company_name: str, cache: dict) -> str | None:
    """Résout un ticker Yahoo Finance depuis un ISIN ou un nom d'entreprise."""
    isin = str(isin).strip() if isin and pd.notna(isin) else ''
    name = str(company_name).strip() if company_name and pd.notna(company_name) else ''
    key  = isin if len(isin) > 5 else name
    if not key:
        return None
    if key in cache:
        return cache[key]

    ticker = None
    # Tentative 1 : ISIN
    if len(isin) > 5:
        try:
            res    = yq_search(isin, first_quote=True)
            ticker = res.get('symbol') if isinstance(res, dict) else None
        except Exception:
            pass
    # Tentative 2 : nom
    if not ticker and name:
        try:
            res    = yq_search(name, first_quote=True)
            ticker = res.get('symbol') if isinstance(res, dict) else None
        except Exception:
            pass

    cache[key] = ticker
    return ticker


def resolve_tickers_parallel(
    rows: list[dict],          # [{'isin': ..., 'name': ...}, ...]
    cache: dict,
    max_workers: int = 10,
    progress_cb=None,          # callable(done, total) optionnel
) -> list[str | None]:
    """Résout les tickers en parallèle et met à jour le cache."""
    n       = len(rows)
    results = [None] * n

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(get_ticker, r['isin'], r['name'], cache): i
            for i, r in enumerate(rows)
        }
        done = 0
        for future in as_completed(futures):
            idx         = futures[future]
            results[idx] = future.result()
            done        += 1
            if progress_cb:
                progress_cb(done, n)
            time.sleep(0.02)

    return results


# ══════════════════════════════════════════════════════════════════════════════
# TÉLÉCHARGEMENT PRIX JOURNALIERS
# ══════════════════════════════════════════════════════════════════════════════

def build_periods(years: list[int]) -> dict:
    """
    Construit dynamiquement les périodes à partir d'une liste d'années.
    Ex: [2023, 2024, 2025] →
        {'2023': ('2023-01-01','2023-12-31'),
         '2024': ('2024-01-01','2024-12-31'),
         '2025': ('2025-01-01','2025-12-31'),
         '2023_2025': ('2023-01-01','2025-12-31')}
    """
    years = sorted(set(years))
    periods = {}
    for y in years:
        periods[str(y)] = (f'{y}-01-01', f'{y}-12-31')
    if len(years) >= 2:
        label = f'{years[0]}_{years[-1]}'
        periods[label] = (f'{years[0]}-01-01', f'{years[-1]}-12-31')
    return periods


def download_prices(
    tickers: list[str],
    start_date: str,
    end_date: str,
    chunk_size: int = 500,
    progress_cb=None,
) -> pd.DataFrame:
    """
    Télécharge les prix de clôture ajustés via yfinance par blocs.
    Retourne un DataFrame date×ticker.
    """
    valid   = [t for t in tickers if t and pd.notna(t)]
    chunks  = [valid[i:i+chunk_size] for i in range(0, len(valid), chunk_size)]
    frames  = []
    n_blocs = len(chunks)

    for i, chunk in enumerate(chunks):
        try:
            raw = yf.download(
                chunk, start=start_date, end=end_date,
                auto_adjust=True, progress=False
            )
            if isinstance(raw.columns, pd.MultiIndex):
                close = raw['Close']
            else:
                close = raw[['Close']].rename(columns={'Close': chunk[0]})
            frames.append(close)
        except Exception as e:
            print(f"  [download_prices] Erreur bloc {i+1}/{n_blocs}: {e}")
        if progress_cb:
            progress_cb(i + 1, n_blocs)

    if not frames:
        return pd.DataFrame()

    prices = pd.concat(frames, axis=1)
    prices = prices.loc[:, ~prices.columns.duplicated()]
    prices.index = pd.to_datetime(prices.index)
    return prices.sort_index()


# ══════════════════════════════════════════════════════════════════════════════
# FONDAMENTAUX (MarketCap, Book-to-Market)
# ══════════════════════════════════════════════════════════════════════════════

def fetch_fundamentals(ticker: str) -> dict:
    try:
        info  = yf.Ticker(ticker).info
        price = (info.get('currentPrice')
                 or info.get('regularMarketPrice')
                 or info.get('previousClose'))
        bv    = info.get('bookValue')
        mc    = info.get('marketCap')
        btm   = (bv / price) if (bv and price and price > 0) else None
        return {'ticker': ticker, 'MarketCap': mc, 'BookToMarket': btm}
    except Exception:
        return {'ticker': ticker, 'MarketCap': None, 'BookToMarket': None}


def fetch_all_fundamentals(
    tickers: list[str],
    max_workers: int = 10,
    progress_cb=None,
) -> pd.DataFrame:
    records = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_fundamentals, t): t for t in tickers}
        done    = 0
        for future in as_completed(futures):
            records.append(future.result())
            done += 1
            if progress_cb:
                progress_cb(done, len(tickers))

    df = pd.DataFrame(records)
    df = df.drop_duplicates(subset='ticker', keep='first').reset_index(drop=True)
    df['LogMarketCap'] = np.log(df['MarketCap'].replace(0, np.nan))
    return df


# ══════════════════════════════════════════════════════════════════════════════
# CALCUL MÉTRIQUES FINANCIÈRES
# ══════════════════════════════════════════════════════════════════════════════

def calc_return(px: pd.Series) -> float:
    r = px.pct_change().dropna()
    return float(np.prod(1 + r) - 1) if len(r) >= 50 else np.nan

def calc_vol(px: pd.Series) -> float:
    r = px.pct_change().dropna()
    return float(r.std() * np.sqrt(252)) if len(r) >= 50 else np.nan

def calc_sharpe(px: pd.Series, rf: float = 0.0) -> float:
    r = px.pct_change().dropna()
    if len(r) < 50:
        return np.nan
    ann_ret = float(np.prod(1 + r) - 1)
    ann_vol = float(r.std() * np.sqrt(252))
    return (ann_ret - rf) / ann_vol if ann_vol > 0 else np.nan

def calc_max_drawdown(px: pd.Series) -> float:
    px = px.dropna()
    if len(px) < 50:
        return np.nan
    return float(((px - px.cummax()) / px.cummax()).min())


def compute_financial_metrics(
    df_scores: pd.DataFrame,
    prices: pd.DataFrame,
    periods: dict,
    company_col: str,
    ticker_col: str = 'ticker',
) -> pd.DataFrame:
    """
    Calcule rendement, vol, Sharpe, MDD pour chaque période et chaque entreprise.
    Retourne un DataFrame avec les mêmes index que df_scores.
    """
    records = []
    for _, row in df_scores.iterrows():
        t   = row.get(ticker_col)
        rec = {company_col: row[company_col], ticker_col: t}
        if pd.notna(t) and str(t) != 'None' and t in prices.columns:
            for period, (start, end) in periods.items():
                px = prices[t].loc[start:end].dropna()
                rec[f'Rendement_{period}']   = calc_return(px)
                rec[f'Volatilite_{period}']  = calc_vol(px)
                rec[f'Sharpe_{period}']      = calc_sharpe(px)
                rec[f'MaxDrawdown_{period}'] = calc_max_drawdown(px)
        else:
            for period in periods:
                for m in ('Rendement', 'Volatilite', 'Sharpe', 'MaxDrawdown'):
                    rec[f'{m}_{period}'] = np.nan
        records.append(rec)

    return pd.DataFrame(records)


def add_quintiles(
    df: pd.DataFrame,
    score_col: str,
    quintile_col: str,
    filter_mask: pd.Series | None = None,
) -> pd.DataFrame:
    """Ajoute une colonne quintile Q1–Q5 sur les lignes filtrées."""
    mask = (
        filter_mask
        if filter_mask is not None
        else df[score_col].notna()
    )
    if mask.sum() >= 5:
        df.loc[mask, quintile_col] = pd.qcut(
            df.loc[mask, score_col],
            q=5, labels=['Q1', 'Q2', 'Q3', 'Q4', 'Q5']
        ).astype(str)
    return df


def clean_for_parquet(df: pd.DataFrame) -> pd.DataFrame:
    """Convertit les colonnes object en str pour compatibilité Parquet."""
    for col in df.select_dtypes(include='object').columns:
        converted = pd.to_numeric(df[col], errors='coerce')
        if converted.notna().sum() / max(len(df), 1) > 0.5:
            df[col] = converted
        else:
            df[col] = df[col].astype(str)
    return df
