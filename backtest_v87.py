"""V8.7: backtest exploratoire historique des trois configurations techniques.
Règles calculées sans prix futurs, signal à la clôture J, achat à l'ouverture J+1.
Pas de données fondamentales historiques point-in-time: aucune conclusion sur le scoring V8.6.
Simulation par titre, pas de portefeuille multi-titres réaliste.
"""
from __future__ import annotations
import json, math
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data'; CONF=ROOT/'config'; HIST=DATA/'historique_long'

def load_history(path):
    df=pd.read_csv(path,index_col='Date',parse_dates=['Date']).sort_index()
    cols=['Open','High','Low','Close','Volume','Adj Close']
    if df.index.has_duplicates or len(df)<260 or any(x not in df for x in cols):
        raise ValueError('HISTORIQUE_INSUFFISANT_OU_INVALIDE')
    if df[cols].isna().any().any() or (df[['Open','High','Low','Close','Adj Close']]<=0).any().any():
        raise ValueError('PRIX_INVALIDE')
    if (df.Volume<0).any():raise ValueError('VOLUME_INVALIDE')
    # Les indicateurs sont construits sur la série ajustée; les prix ajustés
    # sont une approximation et ne reconstituent pas fidèlement une exécution réelle.
    f=df['Adj Close']/df.Close
    for c in ('Open','High','Low','Close'):
        df[c]=df[c]*f
    if (df.Open/df.Close.shift(1)-1).abs().gt(.30).any():
        raise ValueError('GAP_AJUSTE_EXTREME')
    return df[['Open','High','Low','Close','Volume']]

def tax_status(ticker, tax):
    if ticker in tax['oui'] and ticker in tax['non']:
        raise ValueError('TTF_CONTRADICTOIRE')
    if ticker in tax['oui']:return 'HYPOTHESE_OUI'
    if ticker in tax['non']:return 'HYPOTHESE_NON'
    return 'INCONNUE'

def simulate(d, strategy, cfg, status):
    from backtest import indicators, signal
    # Par prudence ne simule pas les sociétés à statut fiscal inconnu.
    if status=='INCONNUE':return [],'TTF_INCONNUE'
    base=cfg['backtest']; f=indicators(d)
    fee=cfg['frais_pct_par_ordre']/100; slip=cfg['slippage_pct_par_cote']/100
    ttf=cfg['ttf_pct']/100 if status=='HYPOTHESE_OUI' else 0
    trades=[]; i=205
    while i<len(d)-1:
        row=f.iloc[i]
        if not signal(row,strategy,{'min_turnover_eur':cfg['liquidite_min_eur']}):
            i+=1;continue
        ent_i=i+1; entry=float(d.Open.iloc[ent_i])*(1+slip)
        atr=float(row.atr)
        if not(math.isfinite(entry) and entry>0 and math.isfinite(atr) and atr>0):
            i+=1;continue
        # Stop technique candidat: sous le plus haut support pertinent ou 1,5 ATR.
        supports=[float(z) for z in (row.ma50,row.low20) if pd.notna(z) and 0<z<entry]
        if not supports:i+=1;continue
        technical=max(supports)-cfg['marge_sous_support_atr']*atr
        stop=min(technical,entry-cfg['stop_atr_min_multiple']*atr)
        if stop<=0:i+=1;continue
        risk_unit=entry*(1+fee+ttf)-stop*(1-slip)*(1-fee)
        if risk_unit<=0:i+=1;continue
        qty=min(math.floor((cfg['risque_par_position_eur']+1e-8)/risk_unit),
                math.floor((cfg['capital_eur']+1e-8)/(entry*(1+fee+ttf))))
        if qty<1:i+=1;continue
        last=min(ent_i+base['max_conservation_seances']-1,len(d)-1)
        exit_i=last;exit_px=float(d.Close.iloc[last])*(1-slip);reason='TEMPS'
        for j in range(ent_i,last+1):
            op=float(d.Open.iloc[j]); lo=float(d.Low.iloc[j])
            if op<=stop:exit_i=j;exit_px=op*(1-slip);reason='GAP_STOP';break
            if lo<=stop:exit_i=j;exit_px=stop*(1-slip);reason='STOP';break
        pnl=qty*(exit_px*(1-fee)-entry*(1+fee+ttf))
        trades.append({'ticker':None,'strategie':strategy,'signal':str(d.index[i].date()),'achat':str(d.index[ent_i].date()),
            'vente':str(d.index[exit_i].date()),'quantite':qty,'prix_achat_ajuste':round(entry,5),
            'stop_ajuste':round(stop,5),'prix_vente_ajuste':round(exit_px,5),
            'pnl_net_eur':round(pnl,2),'risque_initial_eur':round(qty*risk_unit,2),
            'taxe_hypothese':status,'raison_sortie':reason})
        i=exit_i+1
    return trades,None

def summarize(trades, min_count):
    if not trades:return {'trades':0,'statut':'ECHANTILLON_INSUFFISANT'}
    x=np.array([t['pnl_net_eur'] for t in trades],dtype=float)
    plus=x[x>0].sum();minus=abs(x[x<0].sum())
    return {'trades':len(x),'taux_reussite_pct':round(100*float((x>0).mean()),2),
        'pnl_net_eur_somme_trades':round(float(x.sum()),2),'gain_moyen_eur':round(float(x.mean()),2),
        'profit_factor':round(float(plus/minus),3) if minus>0 else None,
        'statut':'EXPLORATOIRE' if len(x)>=min_count else 'ECHANTILLON_INSUFFISANT'}

def run():
    cfg=json.loads((CONF/'v88.json').read_text()); tax=json.loads((CONF/'ttf_2026.json').read_text())
    watch=json.loads((CONF/'watchlist.json').read_text()); names=sorted(set(sum((watch.get(k,[]) for k in ('cac40_indicatif','actions_supplementaires')),[])))
    findings={};errors={};all_trades={s:[] for s in cfg['backtest']['strategies']}
    for ticker in names:
        try:
            d=load_history(HIST/(ticker+'.csv'))
            status=tax_status(ticker,tax)
            findings[ticker]={}
            for st in cfg['backtest']['strategies']:
                trades,skip=simulate(d,st,cfg,status)
                for t in trades:t['ticker']=ticker
                all_trades[st].extend(trades)
                findings[ticker][st]={'resume':summarize(trades,cfg['backtest']['min_trades_conclusions']),
                    'limite':skip,'derniers_trades':trades[-5:]}
        except Exception as e:errors[ticker]=str(e)[:160]
    result={'schema_version':'8.7','genere_utc':datetime.now(timezone.utc).isoformat(),
        'univers_configure':len(names),'titres_calcules':len(findings),'erreurs':errors,
        'strategies':{k:summarize(v,cfg['backtest']['min_trades_conclusions']) for k,v in all_trades.items()},
        'titres':findings,'achats_autorises':0,
        'avertissements':['SIMULATIONS INDEPENDANTES PAR TITRE: PAS DE PORTEFEUILLE NI RISQUE CUMULE SIMULE',
         'SOMMES DE PNL NON INVESTISSABLES SIMULTANEMENT; CAGR SHARPE SORTINO CALMAR NON CALCULES SANS EQUITY CURVE',
         'UNIVERS ACTUEL: BIAIS DE SURVIVANCE; SIGNAUX TECHNIQUES UNIQUEMENT; PAS DE FUNDAMENTAUX POINT-IN-TIME',
         'COURS AJUSTES POUR COMPARABILITE, MAIS EXECUTIONS REELLES ET TTF HISTORIQUE NON RECONSTITUEES',
         'PAS DE RATIO DE GAIN/RISQUE 2 GARANTI PAR STRATEGIE HISTORIQUE; AUCUN ACHAT AUTORISE']}
    (DATA/'backtest_v87.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
    print('V8.7',len(findings),'titres',len(errors),'erreurs',result['strategies'])
    return result
if __name__=='__main__':run()
