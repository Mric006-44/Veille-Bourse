"""V8.3: Recherche seulement; top 5 global et top 5 par strategie.
Compatible avec sorties existantes V4 / V7.3 / V8. Aucune autorisation d'achat.
"""
from __future__ import annotations
import json, math
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
CONF = ROOT / 'config' / 'analyse_v83.json'
OUTPUT = DATA / 'rapport_chatgpt_v83.json'

def num(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (ValueError, TypeError):
        return None

def percentage(x):
    v = num(x)
    return None if v is None else round(100*v, 2)

def ratio(a, b):
    a, b = num(a), num(b)
    return round(a / b, 6) if a is not None and b is not None and b > 0 else None

def enriched_technical(ticker, base, history_dir=DATA / 'historique'):
    result = {k:base.get(k) for k in ('performance_20j_pct','performance_60j_pct', 'rsi14','adx14','macd_histogramme',
                'mm20','mm50','mm200','atr14','close','ratio_volume_20j','plus_haut_20j_precedent',
                'valeur_echangee_moyenne20_eur_estimee')}
    result.update({k:None for k in ('performance_126j_pct','performance_252j_pct','volatilite_20j_pct',
            'volatilite_60j_pct','plus_haut_252j_precedent','plus_bas_252j_precedent')})
    path = history_dir / f'{ticker}.csv'
    if not path.exists():
        return result
    try:
        df = pd.read_csv(path, index_col='Date', parse_dates=['Date']).sort_index()
        c = pd.to_numeric(df['Close'], errors='coerce')
        h = pd.to_numeric(df['High'], errors='coerce')
        l = pd.to_numeric(df['Low'], errors='coerce')
        if c.isna().any() or (c <= 0).any() or h.isna().any() or l.isna().any():
            return result
        for n in (126,252):
            if len(c)>n:
                result[f'performance_{n}j_pct']=round(100*(c.iloc[-1]/c.iloc[-n-1]-1),2)
        returns=c.pct_change(fill_method=None)
        for n in (20,60):
            if returns.tail(n).notna().sum()==n:
                result[f'volatilite_{n}j_pct']=round(returns.tail(n).std(ddof=1)*(252**.5)*100,2)
        if len(c)>252:
            result['plus_haut_252j_precedent']=round(float(h.iloc[-253:-1].max()),4)
            result['plus_bas_252j_precedent']=round(float(l.iloc[-253:-1].min()),4)
    except (OSError, ValueError, KeyError, pd.errors.ParserError):
        pass
    return result

def enrich_fundamental(record):
    d=(record or {}).get('donnees') or {}
    solid=d.get('solidite') or {}; identity=d.get('identite') or {}; val=d.get('valorisation') or {}
    fin = identity.get('sector') in ('Financial Services','Financials')
    net_debt = (num(solid.get('totalDebt'))-num(solid.get('totalCash'))
                if num(solid.get('totalDebt')) is not None and num(solid.get('totalCash')) is not None else None)
    marketcap = num(identity.get('marketCap'))
    fcf = num(solid.get('freeCashflow'))
    metrics = {
        'dette_nette': round(net_debt,2) if net_debt is not None and not fin else None,
        'fcf_yield_pct': round(100*fcf/marketcap,2) if fcf is not None and marketcap is not None and marketcap>0 and not fin else None,
        'marge_fcf_pct': None,
        'roic_pct': None,
        'piotroski_f_score': None,
        'altman_z_score': None,
        'per_previsionnel': num(val.get('forwardPE')),
        'ev_ebitda': num(val.get('enterpriseToEbitda')),
        'croissance_ca_pct': percentage((d.get('croissance') or {}).get('revenueGrowth')),
        'marge_operationnelle_pct': percentage((d.get('rentabilite') or {}).get('operatingMargins')),
        'roe_pct': percentage((d.get('rentabilite') or {}).get('returnOnEquity')),
        'source': (record or {}).get('source'),
        'date_collecte_utc': (record or {}).get('date_collecte_utc'),
        'donnees_officielles_validees': bool((record or {}).get('valide_par_document_primaire',False))
    }
    # Ne jamais fabriquer un ROIC/Piotroski sans les etats financiers comparables.
    return metrics

def fundamental_score(m, financial=False):
    tests = [
        ('croissance_ca_pct', 15, lambda x:x>0),
        ('marge_operationnelle_pct', 20, lambda x:x>=10),
        ('roe_pct', 20, lambda x:x>=10),
        ('per_previsionnel', 20, lambda x:0<x<=25),
        ('fcf_yield_pct', 25, lambda x:x>=4)
    ]
    if financial:
        tests=[x for x in tests if x[0] not in ('marge_operationnelle_pct','fcf_yield_pct')]
    seen=sum(w for k,w,pred in tests if num(m.get(k)) is not None)
    earned=sum(w for k,w,pred in tests if num(m.get(k)) is not None and pred(num(m[k])))
    total=sum(x[1] for x in tests)
    return (round(100*earned/seen,1) if seen else None,round(100*seen/total,1) if total else 0)

def strategy_checks(name,t,f,cfg):
    checks=[]
    def add(label, value):
        checks.append({'critere':label,'satisfait':value})
    rsi=num(t.get('rsi14')); adx=num(t.get('adx14')); close=num(t.get('close'))
    ma200=num(t.get('mm200')); ma50=num(t.get('mm50')); atr=num(t.get('atr14'))
    hist=num(t.get('macd_histogramme'))
    if name=='croissance_momentum':
        add('RSI',rsi is not None and cfg['rsi_min']<=rsi<=cfg['rsi_max'])
        ret=num(t.get('performance_252j_pct'))
        add('PERFORMANCE_1_AN',ret is not None and ret>=cfg['performance_252j_min_pct'])
        add('ADX',adx is not None and adx>=cfg['adx_min'])
        add('COURS_MM200',close is not None and ma200 is not None and close>ma200)
        add('MACD',hist is not None and hist>0)
        ca=num(f.get('croissance_ca_pct'))
        add('CROISSANCE_CA',ca is not None and ca>cfg['croissance_ca_min_pct'])
    elif name=='value_rebond':
        add('RSI',rsi is not None and cfg['rsi_min']<=rsi<=cfg['rsi_max'])
        pe=num(f.get('per_previsionnel'))
        add('PER_PREVISIONNEL',pe is not None and 0<pe<=cfg['per_forward_max'])
        fc=num(f.get('fcf_yield_pct'))
        add('FCF_YIELD',fc is not None and fc>=cfg['fcf_yield_min_pct'])
        add('PROXIMITE_MM50',all(x is not None for x in (close,ma50,atr)) and atr>0 and abs(close-ma50)<=cfg['rebond_proximite_mm50_atr_max']*atr)
        add('MACD',hist is not None and hist>0)
    elif name=='cassure':
        add('RSI',rsi is not None and cfg['rsi_min']<=rsi<=cfg['rsi_max'])
        add('ADX',adx is not None and adx>=cfg['adx_min'])
        vol=num(t.get('ratio_volume_20j'))
        add('VOLUME_RELATIF',vol is not None and vol>=cfg['ratio_volume_min'])
        high=num(t.get('plus_haut_20j_precedent'))
        add('CASSURE_HAUT20',close is not None and high is not None and close>high)
        add('MACD',hist is not None and hist>0)
    else:
        raise ValueError('Strategie inconnue')
    count=sum(x['satisfait'] for x in checks)
    return checks, round(100*count/len(checks),1)

def validate_config(cfg):
    if cfg.get('version') != '8.3':raise ValueError('Version config invalide')
    risk=cfg['securite_non_modifiable_par_scoring']
    expected={'liquidite_min_20j_eur':1000000,'budget_tactique_total_eur':2000,
        'risque_max_position_eur':20,'risque_max_cumule_eur':60,'positions_max':3,
        'positions_par_secteur_max':2,'ratio_gain_risque_min':2,'frais_achat_pct':0.35,'frais_vente_pct':0.35}
    for key,v in expected.items():
        if risk.get(key)!=v:raise ValueError(f'Regle de risque modifiee: {key}')
    weight=cfg['classement']['ponderation_globale']
    if sum(weight.values())!=100:raise ValueError('Ponderations globales !=100')
    if not (1<=cfg['classement']['max_global']<=5 and 1<=cfg['classement']['max_par_strategie']<=5):
        raise ValueError('Limite de cinq depassee')
    if set(cfg['classement']['strategies'])!={'croissance_momentum','value_rebond','cassure'}:
        raise ValueError('Strategie manquante')

def make_report(v4,v73,v8,cfg,history_dir=DATA/'historique'):
    validate_config(cfg)
    if str(v4.get('schema_version'))!='4.0' or str(v73.get('schema_version'))!='7.3' or str(v8.get('schema_version'))!='8.0':
        raise ValueError('Schema source invalide')
    if v73.get('sources',{}).get('v4')!=v4.get('mise_a_jour_utc'):
        raise ValueError('Source technique desynchronisee')
    old={x['ticker']:x for x in v73.get('univers',[])}
    fiches=v8.get('fiches',{})
    if not old: raise ValueError('Audit V7.3 vide')
    universe=[]
    for ticker,raw in sorted(v4.get('indicateurs',{}).items()):
        previous=old.get(ticker)
        if previous is None:continue
        tech=enriched_technical(ticker,raw,history_dir)
        original=fiches.get(ticker)
        fund=enrich_fundamental(original)
        fin=((original or {}).get('donnees') or {}).get('identite',{}).get('sector') in ('Financial Services','Financials')
        fscore,coverage=fundamental_score(fund,fin)
        strategies={}
        for name,params in cfg['classement']['strategies'].items():
            checks,match=strategy_checks(name,tech,fund,params)
            strategies[name]={'adequation_pct':match,'criteres':checks,'criteres_tous_satisfaits':all(x['satisfait'] for x in checks)}
        liquidity=num(raw.get('valeur_echangee_moyenne20_eur_estimee'))
        blocks=[]
        if liquidity is None or liquidity<cfg['securite_non_modifiable_par_scoring']['liquidite_min_20j_eur']:blocks.append('LIQUIDITE_INSUFFISANTE')
        if not previous.get('retenable_pour_etude'):blocks.append('AUDIT_TECHNIQUE_OU_DATE_NON_CONFORME')
        if cfg['classement']['exclure_anomalies'] and raw.get('anomalies'):blocks.append('ANOMALIES_DONNEES')
        if coverage<cfg['classement']['couverture_fondamentale_min_pct']:
            blocks.append('COUVERTURE_FONDAMENTALE_INSUFFISANTE')
        if fscore is None:blocks.append('SCORE_FONDAMENTAL_INDISPONIBLE')
        technically=num(previous.get('score_exploratoire_100'))
        # Score global: la meilleure adequation strategique, pas de bonus pour la simple presence dans un top.
        better=max(x['adequation_pct'] for x in strategies.values())
        weights=cfg['classement']['ponderation_globale']
        overall=(round((technically*weights['technique']+fscore*weights['fondamental']+better*weights['strategie'])/100,2)
                 if technically is not None and fscore is not None else None)
        universe.append({'ticker':ticker,'date_seance':raw.get('date_seance'),
            'score_global_100':overall,'score_technique_100':technically,
            'score_fondamental_100':fscore,'couverture_fondamentale_pct':coverage,
            'indicateurs_techniques':tech,'indicateurs_fondamentaux':fund,
            'strategies':strategies,'admissible_recherche':not blocks,
            'exclusions_recherche':blocks,'plan_exploratoire_v73':previous.get('plan_exploratoire'),
            'blocages_achat':previous.get('raisons_rejet_et_reserves',[]),
            'statut':'SURVEILLANCE','achat_autorise':False})
    admissible=[x for x in universe if x['admissible_recherche'] and x['score_global_100'] is not None]
    def order(x, strategy=None):
        v=x['score_global_100'] if strategy is None else x['strategies'][strategy]['adequation_pct']*.6+x['score_global_100']*.4
        return (-v,-x['couverture_fondamentale_pct'],x['ticker'])
    top_global=sorted(admissible,key=order)[:cfg['classement']['max_global']]
    top_strategies={}
    for name in cfg['classement']['strategies']:
        ranked=sorted(admissible,key=lambda x:order(x,name))[:cfg['classement']['max_par_strategie']]
        top_strategies[name]=[{**x,'correspondance_integrale':x['strategies'][name]['criteres_tous_satisfaits']} for x in ranked]
    return {'schema_version':'8.3','genere_utc':datetime.now(timezone.utc).isoformat(),
       'date_source_technique':v4.get('mise_a_jour_utc'),'date_source_fondamentale':v8.get('genere_utc'),
       'source':'Yahoo Finance/yfinance source unique; comptes non audites; cours non ajustes',
       'univers_analyse':len(universe),'univers_admissible_recherche':len(admissible),
       'top_5_global':top_global,'top_5_par_strategie':top_strategies,
       'univers':universe,'achats_autorises':0,
       'regles':cfg['securite_non_modifiable_par_scoring'],
       'limites':['Listes de recherche, jamais des achats confirmes',
         'Classement exploratoire non backteste; criteres non satisfaits visibles',
         'Catalyseurs non verifies; fondamentaux Yahoo non certifies',
         'ROIC/Piotroski/Altman indisponibles sans comptes comparables',
         'Cours non ajustes pour performance: dividendes et operations sur titres non corriges',
         'TTF/PEA/spread et positions reelles a verifier avant toute operation']}

def main():
    cfg=json.loads(CONF.read_text(encoding='utf8'))
    v4=json.loads((DATA/'indicateurs.json').read_text(encoding='utf8'))
    v73=json.loads((DATA/'rapport_chatgpt_v73.json').read_text(encoding='utf8'))
    v8=json.loads((DATA/'fondamentaux_v8.json').read_text(encoding='utf8'))
    out=make_report(v4,v73,v8,cfg)
    OUTPUT.write_text(json.dumps(out,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
    print(f"V8.3: {out['univers_analyse']} titres, {len(out['top_5_global'])} top global, "
          + ', '.join(f'{k}={len(v)}' for k,v in out['top_5_par_strategie'].items()))
if __name__=='__main__':main()
