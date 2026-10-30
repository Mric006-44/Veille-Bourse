"""V8.9: portefeuille historique technique 2000 EUR, jamais un historique financier point-in-time.
Simulation exploratoire, univers survivant, fiscalite historique et dividendes imparfaits.
"""
from __future__ import annotations
import json, math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from backtest import indicators, signal
from backtest_v87 import load_history, tax_status
ROOT=Path(__file__).resolve().parent

def simulate_portfolio(series, sectors, tax_map, cfg):
    """Une caisse, un calendrier union, signal J-1 et entrée J, sortie stop puis temps.
    La durée d'exposition est estimée séance par séance; arrêt en gap au prix d'ouverture.
    """
    rules=cfg['simulation']; capital=float(cfg['capital_eur']); cash=capital
    fee=cfg['frais_pct_par_ordre']/100.; slip=cfg['slippage_pct_par_cote']/100.
    ttf=cfg['ttf_pct']/100.; maxhold=rules['max_conservation_seances']
    # On conserve les dates propres à chaque valeur pour ne pas anticiper des séances absentes.
    frames={t:indicators(d) for t,d in series.items()}
    locators={t:{date:i for i,date in enumerate(d.index)} for t,d in series.items()}
    dates=sorted(set().union(*(set(d.index) for d in series.values())))
    portfolio={}; trades=[]; equity=[]; rejects=Counter(); maxrisk=0; maxcount=0
    for date in dates:
        # Évaluation prudente des entrées au prix d'ouverture du jour; capitaux des sorties du jour non réutilisés.
        candidates=[]
        for ticker,d in series.items():
            idx=locators[ticker].get(date)
            if idx is None or idx<206 or ticker in portfolio:continue
            previous=frames[ticker].iloc[idx-1]
            if not np.isfinite(previous['atr']) or previous['atr']<=0:continue
            s=next((x for x in rules['strategies'] if signal(previous,x,{'min_turnover_eur':cfg['liquidite_min_eur']})),None)
            if s is not None:candidates.append((rules['strategies'].index(s),ticker,s,previous))
        for _,ticker,strategy,row in sorted(candidates):
            if len(portfolio)>=cfg['positions_max']:rejects['max_positions']+=1;continue
            sector=sectors.get(ticker,'INCONNU')
            if sum(p['sector']==sector for p in portfolio.values())>=cfg['positions_par_secteur_max']:
                rejects['secteur']+=1;continue
            tax=tax_map.get(ticker,'INCONNUE')
            if tax=='INCONNUE':rejects['ttf_inconnue']+=1;continue
            at=locators[ticker][date]; open_px=float(series[ticker].Open.iloc[at]); atr=float(row['atr'])
            if open_px<=0 or not np.isfinite(open_px):continue
            entry=open_px*(1+slip)
            supports=[float(x) for x in (row['ma50'],row['low20']) if np.isfinite(x) and 0<x<entry]
            if not supports:rejects['support_absent']+=1;continue
            stop=min(max(supports)-cfg['marge_sous_support_atr']*atr,entry-cfg['stop_atr_min_multiple']*atr)
            if not 0<stop<entry:continue
            taxrate=ttf if tax=='HYPOTHESE_OUI' else 0
            risk_one=entry*(1+fee+taxrate)-stop*(1-slip)*(1-fee)
            if risk_one<=0:continue
            used=sum(p['risk'] for p in portfolio.values()); available=cfg['risque_cumule_eur']-used
            q=min(math.floor((cfg['risque_par_position_eur']+1e-9)/risk_one),
                  math.floor((available+1e-9)/risk_one),
                  math.floor((cash+1e-9)/(entry*(1+fee+taxrate))))
            if q<1:rejects['taille_nulle']+=1;continue
            cost=q*entry*(1+fee+taxrate); risk=q*risk_one
            cash-=cost
            portfolio[ticker]={'qty':q,'entry':entry,'stop':stop,'cost':cost,'risk':risk,
                'sector':sector,'strategy':strategy,'day':at,'date':str(date.date())}
            maxrisk=max(maxrisk,sum(p['risk'] for p in portfolio.values()));maxcount=max(maxcount,len(portfolio))
        # Prix de liquidation: le stop/gap prend priorité. Pas de target arbitraire.
        for ticker,pos in list(portfolio.items()):
            idx=locators[ticker].get(date)
            if idx is None:continue
            candle=series[ticker].iloc[idx]; opened=float(candle.Open);low=float(candle.Low)
            reason=None; sell=None
            if opened<=pos['stop']:reason='GAP_STOP';sell=opened*(1-slip)
            elif low<=pos['stop']:reason='STOP';sell=pos['stop']*(1-slip)
            elif idx-pos['day']+1>=maxhold:reason='TEMPS';sell=float(candle.Close)*(1-slip)
            if reason:
                net=pos['qty']*sell*(1-fee)
                cash+=net
                trades.append({'ticker':ticker,'strategie':pos['strategy'],'entree':pos['date'],
                  'sortie':str(date.date()),'motif':reason,'quantite':pos['qty'],
                  'gain_net_eur':round(net-pos['cost'],2),'risque_initial_eur':round(pos['risk'],2)})
                del portfolio[ticker]
        mark=cash
        for ticker,pos in portfolio.items():
            df=series[ticker];idx=df.index.searchsorted(date,side='right')-1
            if idx>=0:mark+=pos['qty']*float(df.Close.iloc[idx])*(1-fee-slip)
        equity.append({'date':date.date().isoformat(),'valeur_eur':round(mark,2),'positions':len(portfolio)})
        if len(portfolio)>cfg['positions_max'] or sum(p['risk'] for p in portfolio.values())>cfg['risque_cumule_eur']+1e-7:raise AssertionError('Risque depasse')
    # Les positions encore ouvertes sont valorisées et non liquidées dans le PnL des trades clos.
    values=np.array([p['valeur_eur'] for p in equity]); peaks=np.maximum.accumulate(np.r_[capital,values])[1:]
    dd=100*(values/peaks-1) if len(values) else np.array([])
    final=float(values[-1]) if len(values) else capital
    days=(pd.Timestamp(equity[-1]['date'])-pd.Timestamp(equity[0]['date'])).days if len(equity)>1 else 0
    cagr=(final/capital)**(365.25/days)-1 if days>0 and final>0 else None
    returns=pd.Series(values,index=pd.to_datetime([p['date'] for p in equity])).pct_change().dropna()
    returns=returns[np.isfinite(returns)]
    sharpe=float(np.sqrt(252)*returns.mean()/returns.std()) if len(returns)>2 and returns.std()>0 else None
    downside=returns.clip(upper=0)
    sortino=float(np.sqrt(252)*returns.mean()/np.sqrt((downside**2).mean())) if len(returns)>2 and (downside**2).mean()>0 else None
    maxdd=float(-dd.min()) if len(dd) else 0
    calmar=float(100*cagr/maxdd) if cagr is not None and maxdd>0 else None
    return {'capital_initial_eur':capital,'valeur_finale_mtm_eur':round(final,2),'pnl_mtm_eur':round(final-capital,2),
      'cagr_pct':round(cagr*100,2) if cagr is not None else None,'max_drawdown_pct':round(maxdd,2),
      'sharpe_indicatif':round(sharpe,3) if sharpe is not None else None,
      'sortino_indicatif':round(sortino,3) if sortino is not None else None,
      'calmar_indicatif':round(calmar,3) if calmar is not None else None,
      'max_positions_observe':maxcount,'max_risque_ouvert_eur':round(maxrisk,2),
      'trades_clos':len(trades),'positions_finales':list(portfolio),
      'rejets':dict(rejects),'equity_curve':equity,'trades':trades}

def main():
    config=json.loads((ROOT/'config'/'v91.json').read_text())
    tax=json.loads((ROOT/'config'/'ttf_2026.json').read_text())
    v8=json.loads((ROOT/'data'/'fondamentaux_v8.json').read_text())
    sectors={t:((v.get('donnees') or {}).get('identite') or {}).get('sector') or 'INCONNU' for t,v in v8.get('fiches',{}).items()}
    watch=json.loads((ROOT/'config'/'watchlist.json').read_text())
    names=sorted(set(watch.get('cac40_indicatif',[])+watch.get('actions_supplementaires',[])))
    series={};error={};statuses={}
    for t in names:
        try:
            series[t]=load_history(ROOT/'data'/'historique_long'/f'{t}.csv')
            statuses[t]=tax_status(t,tax)
        except Exception as e:error[t]=str(e)[:160]
    if not series:raise RuntimeError('Aucun historique exploitable')
    result=simulate_portfolio(series,sectors,statuses,config)
    report={'schema_version':'8.9','genere_utc':datetime.now(timezone.utc).isoformat(),
      'univers_configure':len(names),'univers_valide':len(series),'erreurs_historiques':error,
      'resultat':result,'achats_autorises':0,'limitations':[
      'Classification sectorielle ACTUELLE utilisee uniquement comme contrainte de concentration: biais historique possible',
      'Univers actuel uniquement: biais de survivance; aucun fondamental historique point-in-time',
      'Indices ajustés a posteriori et TTF 2026 appliquee retroactivement: approximations non investissables',
      'Frais 0.35% et slippage hypothese 0.10%; pas de spreads historiques ni dividendes reconstitues',
      'Aucun filtre R/R pour les signaux; objectif de cours non modele; portefeuille explore des signaux techniques',
      'Priorite d entree par ordre de strategie puis ticker, sans connaissance du score historique',
      'AUCUNE PREUVE DE SURPERFORMANCE HORS ECHANTILLON NI RECOMMANDATION D ACHAT']}
    path=ROOT/'data'/'backtest_v89.json';path.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False))
    print('V8.9:',len(series),'historiques',len(result['trades']),'trades',result['valeur_finale_mtm_eur'],'EUR')
    return report
if __name__=='__main__':main()
