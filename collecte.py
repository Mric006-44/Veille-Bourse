"""Veille-Bourse V4: collecte OHLCV, indicateurs, audit technique et liquidite.
Source unique Yahoo Finance: AUCUN signal d'achat n'est automatiquement autorise.
"""
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
BENCHMARK = '^FCHI'


def value(x, places=4):
    try:
        x = float(x)
        return round(x, places) if np.isfinite(x) else None
    except (ValueError, TypeError):
        return None


def universe():
    cfg = json.loads(WATCHLIST.read_text(encoding='utf-8'))
    groups = ['cac40_indicatif', 'actions_supplementaires', 'etf']
    symbols, membership = [], {}
    for group in groups:
        items = cfg.get(group, [])
        if not isinstance(items, list):
            raise ValueError(f'{group} doit etre une liste')
        for raw in items:
            if not isinstance(raw, str) or not re.fullmatch(r'[A-Z0-9^.=\-]{1,25}', raw.strip().upper()):
                raise ValueError(f'Symbole invalide dans {group}: {raw!r}')
            ticker = raw.strip().upper()
            if ticker not in membership:
                membership[ticker] = []
                symbols.append(ticker)
            if group not in membership[ticker]:
                membership[ticker].append(group)
    if not symbols or len(symbols) > 180:
        raise ValueError('Univers vide ou superieur a 180 titres')
    return symbols, membership


def download(ticker):
    df = yf.download(ticker, period='2y', interval='1d', auto_adjust=False,
                     progress=False, threads=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    if df.empty:
        raise ValueError('Historique vide')
    df = df.sort_index()
    if df.index.has_duplicates:
        raise ValueError('DATES_DUPLIQUEES')
    return df


def quality(df):
    issues = []
    if len(df) < 210: issues.append('HISTORIQUE_INSUFFISANT')
    if df[REQUIRED].isna().any().any(): issues.append('VALEUR_MANQUANTE')
    if (df[['Open','High','Low','Close']] <= 0).any().any(): issues.append('COURS_NON_POSITIF')
    if (df['Volume'] < 0).any(): issues.append('VOLUME_NEGATIF')
    if ((df['High'] < df[['Open','Close','Low']].max(axis=1)) |
        (df['Low'] > df[['Open','Close','High']].min(axis=1))).any():
        issues.append('OHLC_INCOHERENT')
    if (df['Volume'].tail(5) == 0).any(): issues.append('VOLUME_NUL_RECENT')
    if (df['Close'].pct_change().abs().tail(30) > .20).any():
        issues.append('VARIATION_EXTREME_A_VERIFIER')
    # Week-ends et certains jours feries toleres, sans affirmer cours du jour.
    age = (datetime.now(ZoneInfo('Europe/Paris')).date() - df.index[-1].date()).days
    if age > 4 or age < 0: issues.append('DONNEES_ANCIENNES_OU_DATE_FUTURE')
    return issues


def wilder(x, n=14):
    return x.ewm(alpha=1/n, adjust=False, min_periods=n).mean()


def indicators(df, benchmark=None):
    c = df['Close'].astype(float)
    h = df['High'].astype(float)
    l = df['Low'].astype(float)
    v = df['Volume'].astype(float)
    delta = c.diff()
    gains, losses = wilder(delta.clip(lower=0)), wilder(-delta.clip(upper=0))
    rs = gains / losses.replace(0, np.nan)
    rsi = 100 - 100/(1+rs)
    rsi = rsi.mask((losses==0)&(gains>0), 100).mask((gains==0)&(losses>0), 0).mask((gains==0)&(losses==0), 50)
    macd = c.ewm(span=12,adjust=False).mean() - c.ewm(span=26,adjust=False).mean()
    signal = macd.ewm(span=9,adjust=False).mean()
    prev = c.shift(1)
    tr = pd.concat([h-l,(h-prev).abs(),(l-prev).abs()],axis=1).max(axis=1)
    atr = wilder(tr)
    # Directional movement / ADX: convention Wilder avec lissage exponentiel alpha=1/14.
    up, down = h.diff(), -l.diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0),up,0.),index=c.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0),down,0.),index=c.index)
    atr_safe = atr.replace(0,np.nan)
    plus_di = 100*wilder(plus_dm)/atr_safe
    minus_di = 100*wilder(minus_dm)/atr_safe
    dx = 100*(plus_di-minus_di).abs()/(plus_di+minus_di).replace(0,np.nan)
    adx = wilder(dx)
    sma20 = c.rolling(20).mean()
    sd20 = c.rolling(20).std(ddof=0)
    upper, lower = sma20+2*sd20, sma20-2*sd20
    vol20 = v.rolling(20).mean()
    turnover20 = (c*v).rolling(20).mean()
    out = {
        'date_seance': str(df.index[-1].date()), 'close':value(c.iloc[-1]),
        'volume':int(v.iloc[-1]), 'volume_moyen_20j':value(vol20.iloc[-1]),
        'ratio_volume_20j':value(v.iloc[-1]/vol20.iloc[-1]) if vol20.iloc[-1]>0 else None,
        'rsi14':value(rsi.iloc[-1],2), 'macd_12_26':value(macd.iloc[-1]),
        'macd_signal9':value(signal.iloc[-1]), 'macd_histogramme':value((macd-signal).iloc[-1]),
        'mm20':value(sma20.iloc[-1]), 'mm50':value(c.rolling(50).mean().iloc[-1]),
        'mm200':value(c.rolling(200).mean().iloc[-1]), 'atr14':value(atr.iloc[-1]),
        'atr_pct':value(100*atr.iloc[-1]/c.iloc[-1],2), 'seances':len(df),
        'adx14':value(adx.iloc[-1],2), 'di_plus14':value(plus_di.iloc[-1],2),
        'di_moins14':value(minus_di.iloc[-1],2),
        'bollinger_superieure20':value(upper.iloc[-1]),
        'bollinger_inferieure20':value(lower.iloc[-1]),
        'bollinger_largeur_pct':value(100*(upper.iloc[-1]-lower.iloc[-1])/sma20.iloc[-1],2),
        'performance_5j_pct':value(100*(c.iloc[-1]/c.iloc[-6]-1),2),
        'performance_20j_pct':value(100*(c.iloc[-1]/c.iloc[-21]-1),2),
        'performance_60j_pct':value(100*(c.iloc[-1]/c.iloc[-61]-1),2),
        'plus_haut_20j_precedent':value(h.shift(1).rolling(20).max().iloc[-1]),
        'plus_haut_55j_precedent':value(h.shift(1).rolling(55).max().iloc[-1]),
        'plus_bas_20j_precedent':value(l.shift(1).rolling(20).min().iloc[-1]),
        'plus_bas_55j_precedent':value(l.shift(1).rolling(55).min().iloc[-1]),
        'pente_mm20_5j_pct':value(100*(sma20.iloc[-1]/sma20.iloc[-6]-1),2),
        'pente_mm50_5j_pct':value(100*(c.rolling(50).mean().iloc[-1]/c.rolling(50).mean().iloc[-6]-1),2),
        'pente_mm200_5j_pct':value(100*(c.rolling(200).mean().iloc[-1]/c.rolling(200).mean().iloc[-6]-1),2),
        'valeur_echangee_moyenne20_eur_estimee':value(turnover20.iloc[-1],2),
        'seances_volume_nul_20j':int((v.tail(20)==0).sum()),
    }
    out['force_relative_cac40_20j_pct'] = None
    out['force_relative_cac40_60j_pct'] = None
    if benchmark is not None:
        # Alignement strict sur dates de seance communes (pas de report de cours).
        paired = pd.concat([c,benchmark['Close']],axis=1,join='inner').dropna()
        if len(paired)>=61 and paired.index[-1].date()==df.index[-1].date():
            for horizon in (20,60):
                asset_ret=paired.iloc[-1,0]/paired.iloc[-1-horizon,0]-1
                index_ret=paired.iloc[-1,1]/paired.iloc[-1-horizon,1]-1
                out[f'force_relative_cac40_{horizon}j_pct']=value(100*(asset_ret-index_ret),2)
    return out


def liquidity_issues(stats, etf=False):
    issues=[]
    amount=stats['valeur_echangee_moyenne20_eur_estimee']
    # Simple filtre exploratoire, pas proxy fiable de la liquidite executable.
    if amount is None or amount < 100_000:
        issues.append('FAIBLE_VALEUR_ECHANGEE_20J')
    if stats['seances_volume_nul_20j'] > 0:
        issues.append('SEANCES_SANS_TRANSACTION')
    if etf:
        issues.append('LIQUIDITE_ETF_A_CONTROLER_SUR_CARNET_ET_SPREAD')
    return issues


def main():
    symbols,memberships=universe()
    OUT.mkdir(parents=True,exist_ok=True)
    HISTORY.mkdir(parents=True,exist_ok=True)
    results,errors,statuses={}, {}, {}
    blocking={'HISTORIQUE_INSUFFISANT','VALEUR_MANQUANTE','COURS_NON_POSITIF',
              'VOLUME_NEGATIF','OHLC_INCOHERENT','DONNEES_ANCIENNES_OU_DATE_FUTURE'}
    try:
        benchmark=download(BENCHMARK)
    except Exception as exc:
        benchmark=None
        print(f'BENCHMARK indisponible: {exc}')
    for ticker in symbols:
        try:
            df=download(ticker)
            issues=quality(df)
            if len(df)<210:
                raise ValueError('Historique insuffisant (<210 seances)')
            stats=indicators(df, benchmark)
            issues.extend(liquidity_issues(stats, 'etf' in memberships[ticker]))
            status='REJETE' if any(x in blocking for x in issues) else 'A_VERIFIER'
            stats.update({'qualite':status,'anomalies':issues,'groupes':memberships[ticker],
                          'validation_independante':False,'autorise_signal_achat':False,
                          'source':'Yahoo Finance via yfinance','prix_ajustes':False,
                          'benchmark_source':'Yahoo Finance ^FCHI (non independant)'})
            export=df.copy()
            export.index=export.index.strftime('%Y-%m-%d')
            cols=REQUIRED+(['Adj Close'] if 'Adj Close' in export else [])
            export[cols].to_csv(HISTORY/f'{ticker}.csv',index_label='Date')
            results[ticker]=stats
            statuses[ticker]=status
            print(f'OK {ticker}: {status}, {issues}')
        except Exception as exc:
            errors[ticker]=str(exc)[:250]
            statuses[ticker]='REJETE'
            print(f'ERREUR {ticker}: {exc}')
    if not results:
        raise RuntimeError('Aucune donnee valide; anciens fichiers preserves')
    payload={'schema_version':'4.0','mise_a_jour_utc':datetime.now(timezone.utc).isoformat(),
             'source':'Yahoo Finance via yfinance (non officiel, possiblement differe)',
             'univers':'config/watchlist.json; CAC 40 indicatif non certifie',
             'benchmark':BENCHMARK,'benchmark_disponible':benchmark is not None,
             'nombre_configure':len(symbols),'nombre_reussi':len(results),
             'statuts':statuses,'indicateurs':results,'erreurs':errors,
             'validation_independante_disponible':False,
             'politique':'Aucun signal achat avant confirmation independante et validation risque'}
    (OUT/'indicateurs.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'FIN V4: {len(results)}/{len(symbols)}, {len(errors)} erreurs')

if __name__=='__main__':
    main()
