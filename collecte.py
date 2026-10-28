"""Veille Bourse V3 : surveillance configurable, historique et garde-fous de qualite."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'data'
HISTORY = OUT / 'historique'
WATCHLIST = ROOT / 'config' / 'watchlist.json'
REQUIRED = ['Open', 'High', 'Low', 'Close', 'Volume']


def read_universe():
    settings = json.loads(WATCHLIST.read_text(encoding='utf-8'))
    groups = ['cac40_indicatif', 'actions_supplementaires', 'etf']
    symbols, membership = [], {}
    for group in groups:
        items = settings.get(group, [])
        if not isinstance(items, list):
            raise ValueError(f'{group} doit etre une liste JSON')
        for raw in items:
            if not isinstance(raw, str) or not re.fullmatch(r'[A-Z0-9^.=\-]{1,25}', raw.strip().upper()):
                raise ValueError(f'Symbole invalide dans {group}: {raw!r}')
            ticker = raw.strip().upper()
            if ticker not in membership:
                membership[ticker] = []
                symbols.append(ticker)
            membership[ticker].append(group)
    if not symbols or len(symbols) > 180:
        raise ValueError('Univers vide ou depassant 180 symboles')
    return symbols, membership


def n(value, digits=4):
    try:
        value = float(value)
        return round(value, digits) if np.isfinite(value) else None
    except (ValueError, TypeError):
        return None


def indicators(df):
    c, h, l, v = (df[k].astype(float) for k in ['Close', 'High', 'Low', 'Volume'])
    delta = c.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)
    rsi = rsi.mask((loss == 0) & (gain > 0), 100).mask((gain == 0) & (loss > 0), 0).mask((gain == 0) & (loss == 0), 50)
    macd = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    sig = macd.ewm(span=9, adjust=False).mean()
    prev = c.shift()
    tr = pd.concat([h-l, (h-prev).abs(), (l-prev).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    vm = v.rolling(20).mean()
    last = df.index[-1]
    return {
        'date_seance': str(last.date()), 'close': n(c.iloc[-1]), 'volume': int(v.iloc[-1]),
        'volume_moyen_20j': n(vm.iloc[-1]), 'ratio_volume_20j': n(v.iloc[-1]/vm.iloc[-1]) if vm.iloc[-1] > 0 else None,
        'rsi14': n(rsi.iloc[-1], 2), 'macd_12_26': n(macd.iloc[-1]),
        'macd_signal9': n(sig.iloc[-1]), 'macd_histogramme': n((macd-sig).iloc[-1]),
        'mm20': n(c.rolling(20).mean().iloc[-1]), 'mm50': n(c.rolling(50).mean().iloc[-1]),
        'mm200': n(c.rolling(200).mean().iloc[-1]), 'atr14': n(atr.iloc[-1]), 'seances': len(df),
    }


def check_quality(df):
    issues = []
    if len(df) < 210: issues.append('HISTORIQUE_INSUFFISANT')
    if df[REQUIRED].isna().any().any(): issues.append('VALEUR_MANQUANTE')
    if (df[['Open', 'High', 'Low', 'Close']] <= 0).any().any(): issues.append('COURS_NON_POSITIF')
    if (df['Volume'] < 0).any(): issues.append('VOLUME_NEGATIF')
    if ((df['High'] < df[['Open','Close','Low']].max(axis=1)) | (df['Low'] > df[['Open','Close','High']].min(axis=1))).any(): issues.append('OHLC_INCOHERENT')
    if (df['Volume'].tail(5) == 0).any(): issues.append('VOLUME_NUL_RECENT')
    if (df['Close'].pct_change().abs().tail(30) > 0.20).any(): issues.append('VARIATION_EXTREME_A_VERIFIER')
    # La collecte est prevue apres cloture : si la derniere seance date de plus de 4 jours, on rejette.
    paris_date = datetime.now(ZoneInfo('Europe/Paris')).date()
    if (paris_date - df.index[-1].date()).days > 4: issues.append('DONNEES_ANCIENNES')
    return issues


def main():
    symbols, groups = read_universe()
    OUT.mkdir(parents=True, exist_ok=True)
    HISTORY.mkdir(parents=True, exist_ok=True)
    results, errors, statuses = {}, {}, {}
    blocking = {'HISTORIQUE_INSUFFISANT', 'VALEUR_MANQUANTE', 'COURS_NON_POSITIF', 'VOLUME_NEGATIF', 'OHLC_INCOHERENT', 'DONNEES_ANCIENNES'}
    for ticker in symbols:
        try:
            df = yf.download(ticker, period='2y', interval='1d', auto_adjust=False, progress=False, threads=False)
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            if df.empty: raise ValueError('Aucune donnee')
            df = df.sort_index()
            issues = check_quality(df)
            if len(df) < 210: raise ValueError('Historique insuffisant (<210 seances)')
            stats = indicators(df)
            status = 'REJETE' if any(issue in blocking for issue in issues) else 'A_VERIFIER'
            stats.update({'qualite': status, 'anomalies': issues, 'groupes': groups[ticker],
                          'validation_independante': False, 'autorise_signal_achat': False,
                          'source': 'Yahoo Finance via yfinance', 'prix_ajustes': False})
            export = df.copy()
            export.index = export.index.strftime('%Y-%m-%d')
            cols = REQUIRED + (['Adj Close'] if 'Adj Close' in export.columns else [])
            export[cols].to_csv(HISTORY / f'{ticker}.csv', index_label='Date')
            results[ticker] = stats
            statuses[ticker] = status
            print(f'OK {ticker} {status} {issues}')
        except Exception as e:
            errors[ticker] = str(e)[:250]
            statuses[ticker] = 'REJETE'
            print(f'ERREUR {ticker}: {e}')
    if not results: raise RuntimeError('Aucune donnee : fichiers existants preserves')
    output = {'schema_version': '3.0', 'mise_a_jour_utc': datetime.now(timezone.utc).isoformat(),
              'source': 'Yahoo Finance via yfinance (non officiel, possiblement differe)',
              'univers': 'CAC 40 indicatif + actions supplementaires + ETF (config/watchlist.json)',
              'nombre_configure': len(symbols), 'nombre_reussi': len(results), 'statuts': statuses,
              'indicateurs': results, 'erreurs': errors,
              'politique': 'Aucun signal d achat avant controle independant et verification du risque'}
    (OUT / 'indicateurs.json').write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'FIN {len(results)}/{len(symbols)} titres ; {len(errors)} erreurs')

if __name__ == '__main__': main()
