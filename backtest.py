"""Backtest V6 exploratoire, sans ordre et sans anticipation des cours futurs.
Signaux en cloture J, entree a l'ouverture J+1; OHLC non ajustes:
les dividendes et operations sur titres ne sont pas modelises. Un seul trade
par valeur a la fois. Pas de simulation d'un portefeuille multi-titres.
"""
import json
import math
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
HIST = ROOT / 'data' / 'historique'
OUT = ROOT / 'data' / 'backtest.json'
CONF = ROOT / 'config' / 'backtest.json'
WATCH = ROOT / 'config' / 'watchlist.json'


def indicators(d):
    c=d.Close
    gain=c.diff().clip(lower=0).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    loss=(-c.diff().clip(upper=0)).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    rs=gain/loss.replace(0,np.nan)
    rsi=100-100/(1+rs)
    rsi=rsi.mask((loss==0)&(gain>0),100).mask((gain==0)&(loss>0),0).mask((gain==0)&(loss==0),50)
    macd=c.ewm(span=12,adjust=False).mean()-c.ewm(span=26,adjust=False).mean()
    hist=macd-macd.ewm(span=9,adjust=False).mean()
    tr=pd.concat([(d.High-d.Low),(d.High-c.shift()).abs(),(d.Low-c.shift()).abs()],axis=1).max(axis=1)
    atr=tr.ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    up=d.High.diff(); down=-d.Low.diff()
    pdm=pd.Series(np.where((up>down)&(up>0),up,0.0),index=d.index)
    mdm=pd.Series(np.where((down>up)&(down>0),down,0.0),index=d.index)
    di_plus=100*pdm.ewm(alpha=1/14,adjust=False,min_periods=14).mean()/atr.replace(0,np.nan)
    di_minus=100*mdm.ewm(alpha=1/14,adjust=False,min_periods=14).mean()/atr.replace(0,np.nan)
    dx=100*(di_plus-di_minus).abs()/(di_plus+di_minus).replace(0,np.nan)
    adx=dx.ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    return pd.DataFrame(dict(close=c,ma50=c.rolling(50).mean(),ma200=c.rolling(200).mean(),rsi=rsi,
        hist=hist,adx=adx,di_plus=di_plus,di_minus=di_minus,atr=atr,
        high20=d.High.shift().rolling(20).max(),low20=d.Low.shift().rolling(20).min(),
        volume_ratio=d.Volume/d.Volume.rolling(20).mean(),
        liquidity=(c*d.Volume).rolling(20).mean(),ret20=c.pct_change(20)),index=d.index)


def signal(row,strategy,config):
    if row.isna().any(): return False
    if row.liquidity < config['min_turnover_eur']: return False
    if strategy=='TENDANCE':
        return bool(row.close>row.ma50>row.ma200 and row.adx>=20 and row.di_plus>row.di_minus and 45<=row.rsi<=70 and row["hist"]>0)
    if strategy=='REBOND_POTENTIEL':
        return bool(abs(row.close-row.ma50)<=row.atr and 35<=row.rsi<=55 and row["hist"]>0 and row.close>row.low20)
    if strategy=='CASSURE':
        return bool(row.close>row.high20 and row.volume_ratio>=1.2 and 50<=row.rsi<=80 and row.ret20>0)
    raise ValueError(strategy)


def simulate(d, strategy, cfg):
    f=indicators(d); trades=[]; i=max(205,30)
    while i < len(d)-1:
        row=f.iloc[i]
        if not signal(row,strategy,cfg): i+=1;continue
        next_i=i+1;entry=float(d.Open.iloc[next_i]); atr=float(row.atr)
        if not (math.isfinite(entry) and entry>0 and math.isfinite(atr) and atr>0): i+=1;continue
        stop=entry-cfg['stop_atr_multiple']*atr
        if stop<=0: i+=1;continue
        fb=cfg['fee_pct']/100; fs=fb
        per_unit=entry*(1+fb)-stop*(1-fs)
        qty=int(cfg['max_risk_eur']//per_unit) if per_unit>0 else 0
        if qty<1:i+=1;continue
        last=min(next_i+cfg['max_holding_sessions']-1,len(d)-1)
        sell_i=last; sell=float(d.Close.iloc[last]); why='TIME_EXIT'
        for j in range(next_i,last+1):
            # Conservative intraday stop fill: if opening gap below stop, exit at open;
            # otherwise exit at stop when day's low breaches it.
            opening=float(d.Open.iloc[j]);low=float(d.Low.iloc[j])
            if opening<=stop: sell_i=j;sell=opening;why='GAP_BELOW_STOP';break
            if low<=stop: sell_i=j;sell=stop;why='STOP';break
        pnl=qty*(sell*(1-fs)-entry*(1+fb))
        trades.append({'signal_date':str(d.index[i].date()),'entry_date':str(d.index[next_i].date()),
                       'exit_date':str(d.index[sell_i].date()),'entry':round(entry,4),'exit':round(sell,4),
                       'quantity':qty,'pnl_eur':round(pnl,2),'reason':why,
                       'risk_at_stop_eur':round(qty*per_unit,2)})
        i=sell_i+1
    return trades


def aggregate(trades):
    if not trades:return {'trades':0,'status':'ECHANTILLON_INSUFFISANT'}
    x=np.array([t['pnl_eur'] for t in trades]);eq=np.cumsum(x); peak=np.maximum.accumulate(np.r_[0,eq]); dd=peak[1:]-eq
    return {'trades':len(trades),'wins_pct':round(100*float((x>0).mean()),2),
            'net_pnl_eur':round(float(x.sum()),2),'avg_pnl_eur':round(float(x.mean()),2),
            'profit_factor':round(float(x[x>0].sum()/abs(x[x<0].sum())),3) if (x<0).any() else None,
            'max_drawdown_eur_sequential':round(float(dd.max()),2),
            'status':'ECHANTILLON_INSUFFISANT' if len(trades)<30 else 'EXPLORATOIRE'}


def main():
    cfg=json.loads(CONF.read_text(encoding='utf-8'))
    watch=json.loads(WATCH.read_text(encoding='utf-8'))
    names=sorted(set(sum((watch.get(k,[]) for k in ('cac40_indicatif','actions_supplementaires','etf')),[])))
    out={'schema_version':'6.0','generated_utc':datetime.now(timezone.utc).isoformat(),
         'rules':cfg,'tickers':{},'errors':{},'caveats':[
             'Historique dynamique du portefeuille actuel: biais de survivance (survivorship bias)',
             'Aucun cout de spread ni slippage; dividendes, splits et OPA non modelises',
             'Aucune simulation de portefeuille global ou de risque cumule 60 EUR',
             'Signal fin de seance, execution ouverture suivante; stop simule sans garantie',
             'Pas de resultat hors-echantillon ou de demonstration de robustesse',
             'AUCUNE RECOMMANDATION OU AUTORISATION D ACHAT']}
    for ticker in names:
        try:
            path=HIST/(ticker+'.csv')
            if not path.exists():raise ValueError('Historique manquant')
            d=pd.read_csv(path,parse_dates=['Date'],index_col='Date').sort_index()
            if d.index.has_duplicates or len(d)<260:raise ValueError('Dates dupliquees ou historique trop court')
            if d[['Open','High','Low','Close','Volume']].isna().any().any():raise ValueError('OHLCV incomplet')
            # Split/dividend gap warning, fail closed if absolute overnight gap > 30%.
            if (d.Open/d.Close.shift()-1).abs().gt(.30).any():raise ValueError('Gap > 30%, verifier operations sur titres')
            rec={}
            for strategy in ['TENDANCE','REBOND_POTENTIEL','CASSURE']:
                trades=simulate(d,strategy,cfg)
                rec[strategy]={'metrics':aggregate(trades),'trades':trades[-cfg['max_trades_per_ticker_strategy']:]}
            out['tickers'][ticker]=rec
        except Exception as ex:out['errors'][ticker]=str(ex)[:220]
    if not out['tickers']:raise RuntimeError('Aucun historique valide: pas de publication')
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    print('V6 backtest:',len(out['tickers']),'titres,',len(out['errors']),'erreurs')

if __name__=='__main__':main()
