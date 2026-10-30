"""V8.6: états financiers annuels Yahoo, indicateurs calculables seulement. Aucun achat.
Ne pas interpréter ces états comme des publications officielles ni comme des données point-in-time.
"""
from __future__ import annotations
import json, math, time
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data'
CONFIG=ROOT/'config'/'analyse_v86.json'
INCOME={
  'revenue':['Total Revenue','Operating Revenue'],
  'gross_profit':['Gross Profit'],
  'ebit':['EBIT','Operating Income'],
  'net_income':['Net Income','Net Income Common Stockholders'],
  'tax_provision':['Tax Provision'],
  'pretax_income':['Pretax Income']}
BALANCE={
  'assets':['Total Assets'],
  'equity':['Stockholders Equity','Total Equity Gross Minority Interest','Common Stock Equity'],
  'debt':['Total Debt','Long Term Debt And Capital Lease Obligation'],
  'cash':['Cash Cash Equivalents And Short Term Investments','Cash And Cash Equivalents'],
  'current_assets':['Current Assets'],
  'current_liabilities':['Current Liabilities'],
  'shares':['Ordinary Shares Number','Share Issued']}
CASHFLOW={
  'cfo':['Operating Cash Flow'],
  'fcf':['Free Cash Flow'],
  'capex':['Capital Expenditure']}

def valid(x):
    try:
        x=float(x)
        return x if math.isfinite(x) else None
    except (ValueError,TypeError):return None

def row(frame,aliases,date):
    if frame is None or getattr(frame,'empty',True):return None
    for key in aliases:
        if key in frame.index and date in frame.columns:
            x=valid(frame.at[key,date])
            if x is not None:return x
    return None

def columns(frame):
    if frame is None or getattr(frame,'empty',True):return []
    return [pd.Timestamp(c) for c in frame.columns if not pd.isna(c)]

def normalize_frames(frames):
    return [f.rename(columns={c:pd.Timestamp(c) for c in f.columns}) if f is not None and not f.empty else pd.DataFrame() for f in frames]

def annual_metrics(income,balance,cashflow):
    income,balance,cashflow=normalize_frames((income,balance,cashflow))
    years=sorted(set(columns(income)) & set(columns(balance)) & set(columns(cashflow)),reverse=True)
    history=[]
    for dt in years:
        record={'date_cloture':dt.strftime('%Y-%m-%d')}
        for k,aliases in INCOME.items():record[k]=row(income,aliases,dt)
        for k,aliases in BALANCE.items():record[k]=row(balance,aliases,dt)
        for k,aliases in CASHFLOW.items():record[k]=row(cashflow,aliases,dt)
        if record['fcf'] is None and record['cfo'] is not None and record['capex'] is not None:
            record['fcf']=record['cfo']-abs(record['capex'])
        history.append(record)
    def div(a,b):
        a,b=valid(a),valid(b)
        return a/b if a is not None and b is not None and b!=0 else None
    def diff(a,b):
        return (a-b) if a is not None and b is not None else None
    def ratio(a,b):
        return div(a,b)
    def pos(x):return x is not None and x>0
    latest=history[0] if history else {}
    prior=history[1] if len(history)>1 else {}
    third=history[3] if len(history)>=4 else {}
    profit=latest.get('net_income'); old_profit=prior.get('net_income')
    assets=latest.get('assets'); old_assets=prior.get('assets')
    roa=div(profit,assets); old_roa=div(old_profit,old_assets)
    cfo=latest.get('cfo')
    # Piotroski 9 critères : score seulement si les neuf sont évaluables.
    criteria={
       'roa_positive':pos(roa) if roa is not None else None,
       'cfo_positive':pos(cfo) if cfo is not None else None,
       'roa_increase':roa>old_roa if roa is not None and old_roa is not None else None,
       'cfo_over_net_income':cfo>profit if cfo is not None and profit is not None else None,
       'leverage_decrease':None,
       'current_ratio_increase':None,
       'no_dilution':None,
       'gross_margin_increase':None,
       'asset_turnover_increase':None}
    new_lev=div(latest.get('debt'),assets);old_lev=div(prior.get('debt'),old_assets)
    if new_lev is not None and old_lev is not None:criteria['leverage_decrease']=new_lev<old_lev
    new_cr=div(latest.get('current_assets'),latest.get('current_liabilities'))
    old_cr=div(prior.get('current_assets'),prior.get('current_liabilities'))
    if new_cr is not None and old_cr is not None:criteria['current_ratio_increase']=new_cr>old_cr
    new_sh=latest.get('shares');old_sh=prior.get('shares')
    if new_sh is not None and old_sh is not None:criteria['no_dilution']=new_sh<=old_sh
    gm=div(latest.get('gross_profit'),latest.get('revenue'))
    old_gm=div(prior.get('gross_profit'),prior.get('revenue'))
    if gm is not None and old_gm is not None:criteria['gross_margin_increase']=gm>old_gm
    at=div(latest.get('revenue'),assets);old_at=div(prior.get('revenue'),old_assets)
    if at is not None and old_at is not None:criteria['asset_turnover_increase']=at>old_at
    f_score=sum(criteria.values()) if all(x is not None for x in criteria.values()) else None
    ebit=latest.get('ebit');pretax=latest.get('pretax_income');tax=latest.get('tax_provision')
    tax_rate=div(tax,pretax)
    # Un taux d'impôt aberrant implique un ROIC indisponible, pas de substitution arbitraire.
    if tax_rate is not None and not 0<=tax_rate<=0.5:tax_rate=None
    def invested(r):
        if not r:return None
        d,e,c=r.get('debt'),r.get('equity'),r.get('cash')
        return (d+e-c) if all(v is not None for v in (d,e,c)) else None
    inv=invested(latest);old_inv=invested(prior)
    avg_inv=(inv+old_inv)/2 if inv is not None and old_inv is not None and inv+old_inv>0 else None
    roic=div(ebit*(1-tax_rate) if ebit is not None and tax_rate is not None else None,avg_inv)
    rev0=latest.get('revenue');rev3=third.get('revenue')
    cagr=((rev0/rev3)**(1/3)-1) if rev0 is not None and rev3 is not None and rev0>0 and rev3>0 else None
    fcf_values=[x['fcf'] for x in history[:3]]
    fcf_positive_3y=all(x>0 for x in fcf_values) if len(fcf_values)==3 and all(x is not None for x in fcf_values) else None
    fcf_margin=div(latest.get('fcf'),rev0)
    return {
      'exercices_disponibles':len(history),
      'date_dernier_exercice':latest.get('date_cloture'),
      'croissance_ca_cagr_3ans_pct':round(cagr*100,2) if cagr is not None else None,
      'roic_pct':round(roic*100,2) if roic is not None else None,
      'marge_fcf_pct':round(fcf_margin*100,2) if fcf_margin is not None else None,
      'fcf_positif_3ans':fcf_positive_3y,
      'dette_nette':diff(latest.get('debt'),latest.get('cash')),
      'dette_nette_sur_ebit':div(diff(latest.get('debt'),latest.get('cash')),ebit) if ebit is not None and ebit>0 else None,
      'piotroski_f_score':f_score,
      'piotroski_criteres':criteria,
      'piotroski_couverture':sum(x is not None for x in criteria.values()),
      'historiques':history,
      'altman_z_score':None,
      'limitations':['Source Yahoo non certifiee','ROIC indicatif: EBIT apres impot / capital investi moyen','F-score indisponible si un critere manque','Les comptes historiques ne sont pas des snapshots point-in-time']}

def run(fetch=None):
    if fetch is None:
        import yfinance as yf
        def fetch(t):
            obj=yf.Ticker(t)
            return obj.income_stmt,obj.balance_sheet,obj.cashflow
    cfg=json.loads(CONFIG.read_text(encoding='utf-8'))
    w=json.loads((ROOT/'config'/'watchlist.json').read_text(encoding='utf-8'))
    tickers=list(dict.fromkeys(t for g in ('cac40_indicatif','actions_supplementaires') for t in w.get(g,[])))
    results={}; errors={};consecutive=0
    for ticker in tickers:
        try:
            frames=fetch(ticker)
            result=annual_metrics(*frames)
            results[ticker]=result
            consecutive=0
        except Exception as exc:
            errors[ticker]=str(exc)[:160]
            consecutive+=1
        if consecutive>=cfg['collecte_comptes']['max_erreurs_consecutives']:
            raise RuntimeError('Trop d erreurs successives Yahoo: ne pas remplacer les donnees publiees')
        if cfg['collecte_comptes']['pause_secondes']:time.sleep(cfg['collecte_comptes']['pause_secondes'])
    output={'schema_version':'8.6-finances','genere_utc':datetime.now(timezone.utc).isoformat(),
         'univers':len(tickers),'fiches':results,'erreurs':errors,'source':'Yahoo Finance / yfinance annual financial statements',
         'valide_officiellement':False,'achats_autorises':0}
    DATA.mkdir(exist_ok=True)
    (DATA/'fondamentaux_v86.json').write_text(json.dumps(output,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
    print('V8.6 états financiers:',len(results),'fiches,',len(errors),'erreurs')
    return output
if __name__=='__main__':run()
