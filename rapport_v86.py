"""V8.5 + V8.6: scoring sectoriel prudent, couverture, 5 candidats par stratégie.
Ne produit aucun ordre et préserve intégralement le rapport V8.3 historique.
"""
from __future__ import annotations
import json, math
from datetime import datetime,timezone,date
from pathlib import Path

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data'
CFG=ROOT/'config'/'analyse_v86.json'
OUT=DATA/'rapport_chatgpt_v86.json'
FINANCIAL_SECTORS={'Financial Services','Financials'}

def n(v):
    try:
        v=float(v)
        return v if math.isfinite(v) else None
    except (TypeError,ValueError):return None

def clamp(x):return min(100,max(0,x))

def sector_bucket(s):
    s=(s or 'Inconnu').strip()
    if s in FINANCIAL_SECTORS:return 'Finance'
    if s in ('Real Estate',):return 'Immobilier'
    return s

def relative_rank(value,pool,ascending=True):
    """0..100, valeur la plus attractive reçoit 100, uniquement comparables de même secteur."""
    valid=sorted(n(v) for v in pool if n(v) is not None)
    if len(valid)<2:return None
    less=sum(v<value for v in valid)
    equal=sum(v==value for v in valid)
    pct=100*(less+equal/2)/len(valid)
    return round(pct if ascending else 100-pct,1)

def evaluate_one(item,annual,industry,sector_metrics,cfg,today=None):
    today=today or date.today()
    tech=n(item.get('score_technique_100'))
    old=n(item.get('score_fondamental_100'))
    old_coverage=n(item.get('couverture_fondamentale_pct')) or 0
    fin=item.get('indicateurs_fondamentaux',{})
    sector=sector_bucket(industry)
    financial=sector=='Finance'
    available=[];missing=[];positive=[]
    # Ne valorise pas ROIC / FCF de banques et assurances comme si c'étaient des industriels.
    qualitative=[('roic_pct',lambda x:x>=10),('piotroski_f_score',lambda x:x>=7),
                 ('croissance_ca_cagr_3ans_pct',lambda x:x>=3),
                 ('fcf_positif_3ans',lambda x:x is True),('marge_fcf_pct',lambda x:x>=5)]
    if financial:qualitative=[('croissance_ca_cagr_3ans_pct',lambda x:x>=3)]
    for key,test in qualitative:
        v=(annual or {}).get(key)
        if key=='fcf_positif_3ans':present= isinstance(v,bool)
        else:present=n(v) is not None
        if present:
            available.append(key)
            if test(v):positive.append(key)
        else:missing.append(key)
    qual_coverage=100*len(available)/len(qualitative)
    qual_score=100*len(positive)/len(available) if available else None
    # Comparateurs d'industrie; on utilise les métriques stables déjà disponibles.
    sector_pe=relative_rank(n(fin.get('per_previsionnel')),sector_metrics.get(sector,{}).get('pe',[]),False) if n(fin.get('per_previsionnel')) is not None and n(fin.get('per_previsionnel'))>0 else None
    sector_roic=relative_rank(n((annual or {}).get('roic_pct')),sector_metrics.get(sector,{}).get('roic',[]),True) if n((annual or {}).get('roic_pct')) is not None and not financial else None
    sector_fcf=relative_rank(n(fin.get('fcf_yield_pct')),sector_metrics.get(sector,{}).get('fcf',[]),True) if n(fin.get('fcf_yield_pct')) is not None and not financial else None
    population=sector_metrics.get(sector,{}).get('count',0)
    if population<cfg['fundamental']['min_paires_comparables_secteur']:
        sector_pe=sector_roic=sector_fcf=None
    comps=[x for x in (sector_pe,sector_roic,sector_fcf) if x is not None]
    peer_score=sum(comps)/len(comps) if comps else None
    solidity=(annual or {}).get('dette_nette_sur_ebit')
    solv_score=100 if solidity is not None and solidity<=1.5 else 60 if solidity is not None and solidity<=3 else 10 if solidity is not None else None
    if financial:solv_score=None
    components={
      'qualite_actuelle':old,
      'qualite_pluriannuelle':round(qual_score,2) if qual_score is not None else None,
      'valorisation_sectorielle':round(peer_score,2) if peer_score is not None else None,
      'solidite':solv_score}
    weights=cfg['fundamental']['poids']
    valid_weights=sum(weights[k] for k,v in components.items() if v is not None)
    maximum=sum(weights.values())
    effective_score=sum(weights[k]*v for k,v in components.items() if v is not None)/maximum
    coverage=round(100*valid_weights/maximum,1)
    # double pénalité de couverture: anciens indicateurs + nouvelles sources
    combined_coverage=round((coverage+old_coverage)/2,1)
    freshness='NON_DISPONIBLE'
    if (annual or {}).get('date_dernier_exercice'):
        try:
            age=(today-date.fromisoformat(annual['date_dernier_exercice'])).days
            freshness='A_JOUR' if 0<=age<=cfg['anciennete_comptes_max_mois']*31 else 'COMPTES_ANCIENS'
        except ValueError:freshness='DATE_INVALIDE'
    if freshness!='A_JOUR':
        # Les fondamentaux de Yahoo V8 restent visibles, mais sans confirmer de dossier.
        missing.append('COMPTES_PLURIANNUELS_RECENTS')
    fundamental_adj=round(clamp(effective_score*combined_coverage/100),2)
    matching=max((n(x.get('adequation_pct')) or 0 for x in item.get('strategies',{}).values()),default=0)
    w=cfg['poids']
    score=round(((tech or 0)*w['technique']+fundamental_adj*w['fondamental']+matching*w['adequation_strategie'])/100,2)
    blocks=list(item.get('exclusions_recherche',[]))
    if n(item.get('indicateurs_techniques',{}).get('valeur_echangee_moyenne20_eur_estimee')) is None or n(item['indicateurs_techniques']['valeur_echangee_moyenne20_eur_estimee'])<cfg['liquidite_min_eur_jour']:
        blocks.append('LIQUIDITE_INSUFFISANTE')
    if combined_coverage<cfg['couverture_min_pct']:blocks.append('COUVERTURE_INSUFFISANTE')
    # Manque de comptes ne ferme pas la recherche, mais empêche le statut de candidat complet.
    candidate=not blocks
    return {
      'ticker':item['ticker'],'date_seance':item.get('date_seance'),
      'secteur':sector,'score_v83':item.get('score_global_100'),
      'score_global_v86_100':score,'score_fondamental_prudent_100':fundamental_adj,
      'score_technique_100':tech,'couverture_score_pct':combined_coverage,
      'composantes_fondamentales':components,
      'comparaison_sectorielle':{'nb_societes':population,'per_percentile':sector_pe,'roic_percentile':sector_roic,'fcf_yield_percentile':sector_fcf},
      'indicateurs_pluriannuels':{k:v for k,v in (annual or {}).items() if k not in ('historiques','limitations')},
      'donnees_manquantes':sorted(set(missing)),
      'fraicheur_comptes':freshness,
      'strategies':item.get('strategies',{}),
      'admissible_recherche':candidate,'exclusions_recherche':sorted(set(blocks)),
      'plan_exploratoire_v73':item.get('plan_exploratoire_v73'),
      'blocages_achat':item.get('blocages_achat',[]),
      'statut':'SURVEILLANCE','achat_autorise':False}

def create(old,annual_doc,v8_doc,cfg):
    if str(old.get('schema_version'))!='8.3':raise ValueError('Rapport V8.3 absent ou incompatible')
    if annual_doc.get('schema_version')!='8.6-finances':raise ValueError('Comptes V8.6 absents ou incompatibles')
    if cfg.get('version')!='8.6':raise ValueError('Configuration V8.6 invalide')
    if sum(cfg['poids'].values())!=100 or sum(cfg['fundamental']['poids'].values())!=100:raise ValueError('Pondérations incorrectes')
    if cfg['liquidite_min_eur_jour']!=1000000 or cfg['max_global']>5 or cfg['max_par_strategie']>5:raise ValueError('Règles de sécurité modifiées')
    fiches=v8_doc.get('fiches',{})
    pool={}
    for item in old.get('univers',[]):
        ident=(fiches.get(item['ticker']) or {}).get('donnees',{}).get('identite',{})
        sector=sector_bucket(ident.get('sector'))
        p=pool.setdefault(sector,{'pe':[],'roic':[],'fcf':[],'count':0})
        p['count']+=1
        m=item.get('indicateurs_fondamentaux',{})
        if n(m.get('per_previsionnel')) is not None and n(m['per_previsionnel'])>0:p['pe'].append(n(m['per_previsionnel']))
        if n(m.get('fcf_yield_pct')) is not None:p['fcf'].append(n(m['fcf_yield_pct']))
        roic=n((annual_doc.get('fiches',{}).get(item['ticker']) or {}).get('roic_pct'))
        if roic is not None:p['roic'].append(roic)
    output=[]
    for item in old.get('univers',[]):
        ticker=item['ticker']
        ident=(fiches.get(ticker) or {}).get('donnees',{}).get('identite',{})
        output.append(evaluate_one(item,annual_doc.get('fiches',{}).get(ticker),ident.get('sector'),pool,cfg))
    acceptable=[x for x in output if x['admissible_recherche']]
    acceptable.sort(key=lambda x:(-x['score_global_v86_100'],-x['couverture_score_pct'],x['ticker']))
    shortlist=acceptable[:cfg['max_global']]
    strat={}
    for key in ('croissance_momentum','value_rebond','cassure'):
        def rank(x):
            adeq=n(x['strategies'].get(key,{}).get('adequation_pct')) or 0
            return (-0.65*adeq-0.35*x['score_global_v86_100'],-x['couverture_score_pct'],x['ticker'])
        eligible=sorted(acceptable,key=rank)
        conformes=[x for x in eligible if x['strategies'].get(key,{}).get('criteres_tous_satisfaits') and x['fraicheur_comptes']=='A_JOUR']
        reserve=[x for x in eligible if x not in conformes]
        strat[key]={
          'conformes':conformes[:cfg['max_par_strategie']],
          'surveillance':reserve[:max(0,cfg['max_par_strategie']-min(cfg['max_par_strategie'],len(conformes)))],
          'nb_conformes_total':len(conformes)}
    return {'schema_version':'8.6','genere_utc':datetime.now(timezone.utc).isoformat(),
      'source_v83':old.get('genere_utc'),'source_comptes':annual_doc.get('genere_utc'),
      'univers_analyse':len(output),'univers_admissible_recherche':len(acceptable),
      'top_5_global':shortlist,'top_5_par_strategie':strat,'univers':output,
      'erreurs_collecte_comptes':annual_doc.get('erreurs',{}),
      'achats_autorises':0,'politique':'Classement non backtesté, données Yahoo non certifiées, pas de signal d achat.',
      'limites':['F-score partiel jamais imputé','Comparaisons sectorielles indicatives (classification Yahoo)',
       'Données financières historiques non point-in-time','Pas de validation secondaire des comptes',
       'TTF, PEA, liquidité exécutable, spread, stops et positions à vérifier avant toute décision']}

def main():
    old=json.loads((DATA/'rapport_chatgpt_v83.json').read_text(encoding='utf8'))
    annual=json.loads((DATA/'fondamentaux_v86.json').read_text(encoding='utf8'))
    v8=json.loads((DATA/'fondamentaux_v8.json').read_text(encoding='utf8'))
    cfg=json.loads(CFG.read_text(encoding='utf8'))
    out=create(old,annual,v8,cfg)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
    print('V8.6:',out['univers_analyse'],'titres,',len(out['top_5_global']),'global,',', '.join(k+':'+str(len(v['conformes']))+' conformes' for k,v in out['top_5_par_strategie'].items()))
if __name__=='__main__':main()
