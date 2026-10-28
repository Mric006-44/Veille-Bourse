"""V6.1 : simulation historique exploratoire d'un portefeuille unique.

Ne passe aucun ordre. Les series ajustees Yahoo (Adj Close / Close) sont
une approximation des operations sur titres et dividendes, non un flux exact.
Stop fictif, spread inconnu, aucune execution garantie. Pas de tuning automatique.
"""
from __future__ import annotations
import json
import math
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from backtest import indicators, signal

ROOT = Path(__file__).resolve().parent
HIST = ROOT / 'data' / 'historique'
OUT = ROOT / 'data' / 'portefeuille_backtest.json'
CONFIG = ROOT / 'config' / 'portfolio.json'
WATCH = ROOT / 'config' / 'watchlist.json'


def load_history(path, cfg):
    d = pd.read_csv(path, parse_dates=['Date'], index_col='Date').sort_index()
    cols = ['Open', 'High', 'Low', 'Close', 'Volume', 'Adj Close']
    if any(k not in d for k in cols):
        raise ValueError('Adj Close ou OHLCV absent : impossible de corriger la serie')
    if d.index.has_duplicates or len(d) < cfg['min_adjusted_history_sessions']:
        raise ValueError('Historique trop court ou dates dupliquees')
    if d[cols].isna().any().any() or (d[cols[:4] + ['Adj Close']] <= 0).any().any():
        raise ValueError('Valeurs historiques absentes ou non positives')
    if (d['Volume'] < 0).any():
        raise ValueError('Volume negatif')
    factor = d['Adj Close'] / d['Close']
    if (factor <= 0).any() or (~np.isfinite(factor)).any():
        raise ValueError('Facteur ajustement invalide')
    d = d.copy()
    for name in ['Open', 'High', 'Low', 'Close']:
        d[name] = d[name] * factor
    d = d[['Open', 'High', 'Low', 'Close', 'Volume']]
    if (d['Open'] / d['Close'].shift(1) - 1).abs().gt(cfg['max_overnight_gap_pct'] / 100).any():
        raise ValueError('Gap extreme persistant sur cours ajustes : verification requise')
    return d


def evaluate(data, cfg, benchmark=None):
    """No overlapping position in a ticker; one cash pool and risk pool.

    Signal at close t-1. Entry t open; exits evaluated after entries, so
    proceeds of current-day exits cannot fund current-day entries.
    """
    dates = sorted(set.intersection(*(set(d.index) for d in data.values()))) if data else []
    if len(dates) < 240:
        raise ValueError('Dates communes insuffisantes')
    frames = {t: indicators(d.loc[dates]) for t,d in data.items()}
    frames_data = {t: d.loc[dates] for t,d in data.items()}
    cash = float(cfg['initial_capital_eur'])
    capital0 = cash
    positions = {}
    trades = []
    equity = []
    max_risk_seen = 0.0
    rejected = {'capital': 0, 'risk': 0, 'qty_zero': 0, 'positions': 0}
    fb = cfg['fee_pct_per_side'] / 100
    fs = fb
    slip = cfg['slippage_pct_per_side'] / 100
    prio = cfg['strategy_priority']
    maxhold = cfg['max_holding_sessions']

    for i, dt in enumerate(dates):
        if i >= 205:
            candidates = []
            for ticker, f in frames.items():
                if ticker in positions:
                    continue
                row = f.iloc[i-1]
                # Signal from previous CLOSE, no next-day data.
                match = next((s for s in prio if signal(row, s, {'min_turnover_eur': cfg['min_turnover_eur']})), None)
                if match:
                    candidates.append((prio.index(match), ticker, match, float(row.atr)))
            candidates.sort()
            for _, ticker, strategy, atr in candidates:
                if len(positions) >= cfg['max_positions']:
                    rejected['positions'] += 1
                    continue
                raw = float(frames_data[ticker].Open.iloc[i])
                entry = raw * (1 + slip)
                stop = entry - cfg['stop_atr_multiple'] * atr
                if not (np.isfinite(entry) and np.isfinite(stop) and stop > 0):
                    rejected['qty_zero'] += 1
                    continue
                risk_per = entry*(1+fb) - stop*(1-fs-slip)
                if risk_per <= 0:
                    continue
                risk_used = sum(p['risk'] for p in positions.values())
                available_risk = cfg['max_open_risk_eur'] - risk_used
                if available_risk < risk_per - 1e-9:
                    rejected['risk'] += 1
                    continue
                qty = min(math.floor((cfg['max_risk_per_position_eur']+1e-9)/risk_per),
                          math.floor((available_risk+1e-9)/risk_per),
                          math.floor((cash+1e-9)/(entry*(1+fb))),
                          math.floor(cfg['max_position_value_eur']/entry))
                if qty < 1:
                    rejected['qty_zero'] += 1
                    continue
                debit = qty*entry*(1+fb)
                if debit > cash + 1e-8:
                    rejected['capital'] += 1
                    continue
                cash -= debit
                positions[ticker] = {'ticker':ticker,'strategy':strategy,'qty':qty,'entry':entry,
                    'entry_day':i,'entry_date':dt.date().isoformat(),'stop':stop,
                    'risk':qty*risk_per,'entry_debit':debit}
                max_risk_seen = max(max_risk_seen, sum(p['risk'] for p in positions.values()))
                if max_risk_seen > cfg['max_open_risk_eur'] + 1e-7:
                    raise AssertionError('Risque global depasse')
        for ticker, p in list(positions.items()):
            d = frames_data[ticker]
            op, lo, cl = map(float, (d.Open.iloc[i],d.Low.iloc[i],d.Close.iloc[i]))
            stop = p['stop']
            reason = None
            if op <= stop:
                rawexit = op
                reason = 'GAP_BELOW_STOP'
            elif lo <= stop:
                rawexit = stop
                reason = 'STOP'
            elif i - p['entry_day'] + 1 >= maxhold:
                rawexit = cl
                reason = 'TIME_EXIT'
            elif i == len(dates) - 1:
                rawexit = cl
                reason = 'END_OF_TEST'
            if reason:
                exitprice = rawexit*(1-slip)
                proceeds = p['qty'] * exitprice * (1-fs)
                cash += proceeds
                trades.append({'ticker':ticker,'strategy':p['strategy'],
                    'entry_date':p['entry_date'],'exit_date':dt.date().isoformat(),
                    'quantity':p['qty'],'entry':round(p['entry'],4),'exit':round(exitprice,4),
                    'reason':reason,'risk_theoretical_eur':round(p['risk'],2),
                    'pnl_eur':round(proceeds-p['entry_debit'],2)})
                del positions[ticker]
        e = cash + sum(p['qty']*float(frames_data[t].Close.iloc[i]) for t,p in positions.items())
        equity.append((dt,e))
    if positions:
        raise AssertionError('Positions non cloturees en fin de test')
    eq = pd.Series({d:v for d,v in equity})
    start = max(205, int(len(dates) * (1 - cfg['test_fraction'])))
    split_date = dates[start].date().isoformat()
    results = {}
    for name, sub in [('total',trades), ('chronological_test', [t for t in trades if t['entry_date'] >= split_date])]:
        pnls = [t['pnl_eur'] for t in sub]
        gains = sum(x for x in pnls if x>0)
        losses = sum(x for x in pnls if x<0)
        results[name] = {'trades':len(sub),'win_rate_pct':round(100*sum(x>0 for x in pnls)/len(pnls),2) if pnls else None,
            'net_pnl_eur':round(sum(pnls),2), 'profit_factor':round(gains/abs(losses),3) if losses else None,
            'avg_pnl_eur':round(sum(pnls)/len(pnls),2) if pnls else None}
    drawdown = eq/eq.cummax()-1
    results['total'].update({'max_drawdown_pct_mark_to_market':round(float(drawdown.min()*100),2),
        'return_pct_on_initial_capital':round((cash/capital0-1)*100,2),
        'max_simultaneous_stop_risk_eur':round(max_risk_seen,2)})
    by_strategy = {}
    for s in prio:
        z=[t['pnl_eur'] for t in trades if t['strategy']==s]
        by_strategy[s]={'trades':len(z),'net_pnl_eur':round(sum(z),2)}
    reference = {'status':'UNAVAILABLE', 'note':'Benchmark ^FCHI calcule uniquement si historique fourni et dates alignees'}
    if benchmark is not None:
        series = benchmark['Close'].reindex(dates)
        valid=series.dropna()
        if len(valid)>10 and valid.index[0]==dates[0] and valid.index[-1]==dates[-1]:
            refret=float(valid.iloc[-1]/valid.iloc[0]-1)
            reference={'status':'AVAILABLE','ticker':'^FCHI','return_pct':round(100*refret,2),
                'note':'Indice prix CAC40; non total return et non comparable aux dividendes reinvestis'}
    return {'start_date':dates[0].date().isoformat(),'end_date':dates[-1].date().isoformat(),
        'split_date':split_date, 'metrics':results, 'by_strategy':by_strategy,
        'benchmark':reference, 'rejections':rejected, 'trades':trades,
        'equity_curve':[{'date':d.date().isoformat(),'equity_eur':round(v,2)} for d,v in equity]}


def main():
    cfg=json.loads(CONFIG.read_text(encoding='utf-8'))
    watch=json.loads(WATCH.read_text(encoding='utf-8'))
    tickers=sorted(set(sum((watch.get(k,[]) for k in ('cac40_indicatif','actions_supplementaires','etf')),[])))
    loaded, failures = {}, {}
    for t in tickers:
        try:
            loaded[t] = load_history(HIST / (t+'.csv'),cfg)
        except Exception as e:
            failures[t] = str(e)[:200]
    if len(loaded)<3:
        raise RuntimeError('Moins de 3 titres valides : aucun backtest publie')
    # Separate benchmark fetch; failure does not block portfolio calculation.
    bench=None
    try:
        import yfinance as yf
        b=yf.download('^FCHI',period='2y',interval='1d',auto_adjust=False,progress=False,threads=False)
        if isinstance(b.columns,pd.MultiIndex): b.columns=b.columns.get_level_values(0)
        if not b.empty:
            bench=b[['Close']].sort_index()
            bench.index=bench.index.tz_localize(None)
    except Exception as e:
        print('Benchmark indisponible:',e)
    simulation=evaluate(loaded,cfg,bench)
    output={'schema_version':'6.1','generated_utc':datetime.now(timezone.utc).isoformat(),
        'source':'Yahoo Finance, historiques OHLC ajustes selon ratio Adj Close/Close (approximation)',
        'configuration':cfg,'universe_count':len(tickers),'included_count':len(loaded),
        'excluded':failures, 'portfolio':simulation,
        'limitations':['Biais de survivance de la watchlist actuelle','Pas de validation independante des prix',
           'Ajustement historique par ratio Adj Close/Close : pas de comptabilisation explicite des dividendes, ni verification des splits',
           'Spread inconnu; slippage constant simule','Capital initial fictif, aucune synchronisation avec PEA',
           'Test chronologique descriptif seulement : aucune optimisation des parametres faite en amont',
           'Risque stop theorique <=60 EUR pour entrees; pertes reelles peuvent depasser en cas de gaps',
           'Aucune execution ni recommandation d ordre']}
    OUT.parent.mkdir(exist_ok=True,parents=True)
    OUT.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    p=simulation['metrics']['total'];print('V6.1:',len(loaded),'titres',p['trades'],'trades',p['net_pnl_eur'],'EUR',len(failures),'exclusions')


if __name__ == '__main__':
    main()
