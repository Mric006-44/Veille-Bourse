"""V8.8: dossier de recherche, jamais de passage d'ordre ni d'achat automatique.
Niveaux structurels heuristiques, non confirmés graphiquement; fail closed.
"""
from __future__ import annotations
import json,math
from datetime import date,datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parent; DATA=ROOT/'data'; CONF=ROOT/'config'

def n(x):
    try:
        a=float(x)
        return a if math.isfinite(a) else None
    except (TypeError,ValueError):return None

def tax_status(ticker,tax):
    if ticker in tax['oui'] and ticker in tax['non']:raise ValueError('TTF contradictoire')
    if ticker in tax['oui']:return 'OUI_A_VALIDER_ISIN'
    if ticker in tax['non']:return 'NON_A_VALIDER_ISIN'
    return 'INCONNUE'

def plan(ticker,tech,old,score,annual,cfg,tax,today=None):
    today=today or date.today()
    blocks=[];notes=[]
    if not score.get('admissible_recherche'):blocks.append('NON_ADMISSIBLE_RECHERCHE')
    if n(tech.get('valeur_echangee_moyenne20_eur_estimee')) is None or n(tech['valeur_echangee_moyenne20_eur_estimee'])<cfg['liquidite_min_eur']:
        blocks.append('LIQUIDITE_INSUFFISANTE')
    try:
        age=(today-date.fromisoformat(old.get('date_seance',''))).days
        if not 0<=age<=4:blocks.append('COURS_NON_FRAIS')
    except (ValueError,TypeError):blocks.append('DATE_SEANCE_INVALIDE')
    required=['close','atr14','mm20','mm50','plus_bas_20j_precedent','plus_bas_55j_precedent','plus_haut_20j_precedent','plus_haut_55j_precedent']
    missing=[k for k in required if n(tech.get(k)) is None]
    price=n(tech.get('close'));atr=n(tech.get('atr14'))
    if missing:blocks.append('DONNEES_TECHNIQUES_INCOMPLETES')
    ts=tax_status(ticker,tax)
    if ts=='INCONNUE':blocks.append('TTF_INDETERMINEE')
    # Les statuts par ticker ne constituent jamais une validation juridique ISIN.
    blocks.extend(['TTF_ISIN_NON_VERIFIEE','PEA_NON_VERIFIE','SPREAD_NON_VERIFIE','SOURCE_INDEPENDANTE_ABSENTE',
                   'CATALYSEUR_NON_VALIDE','SIGNAL_GRAPHIQUE_NON_CONFIRME'])
    if cfg['positions_reelles_exhaustives_confirmees'] is not True:blocks.append('REGISTRE_POSITIONS_NON_CONFIRME')
    if not (cfg['verification_pea'] and cfg['verification_spread'] and cfg['validation_source_independante'] and
            cfg['validation_catalyseur'] and cfg['validation_graphique']):
        notes.append('Controle manuel requis; les booleens de configuration ne remplacent pas les justificatifs')
    result={'ticker':ticker,'statut':'SURVEILLANCE' if score.get('admissible_recherche') else 'REJETE_RECHERCHE',
            'achat_autorise':False,'score_global_v86_100':score.get('score_global_v86_100'),
            'strategies':[k for k,x in score.get('strategies',{}).items() if x.get('criteres_tous_satisfaits')],
            'date_seance':old.get('date_seance'),'date_reexamen':'A_FIXER_SELON_CATALYSEUR',
            'fiscalite':ts,'donnees_manquantes':missing,'blocages':sorted(set(blocks)),
            'notes':notes,'plan_exploratoire':None}
    if missing or price is None or atr is None or price<=0 or atr<=0:return result
    supports=sorted({float(x) for k in ('mm20','mm50','plus_bas_20j_precedent','plus_bas_55j_precedent') if (x:=n(tech.get(k))) is not None and 0<x<price},reverse=True)
    resistances=sorted({float(x) for k in ('plus_haut_20j_precedent','plus_haut_55j_precedent') if (x:=n(tech.get(k))) is not None and x>price})
    if not supports:result['blocages'].append('SUPPORT_ABSENT');return result
    if not resistances:result['blocages'].append('OBJECTIF_RESISTANCE_ABSENT');return result
    stop=min(supports[0]-cfg['marge_sous_support_atr']*atr, price-cfg['stop_atr_min_multiple']*atr)
    objective=resistances[0]
    if stop<=0 or stop>=price or objective<=price:result['blocages'].append('NIVEAUX_INVALIDES');return result
    rr=(objective-price)/(price-stop)
    if rr<cfg['ratio_gain_risque_brut_min']:result['blocages'].append('RATIO_BRUT_INSUFFISANT')
    fb=cfg['frais_pct_par_ordre']/100; slip=cfg['slippage_pct_par_cote']/100
    tt=cfg['ttf_pct']/100 if ts=='OUI_A_VALIDER_ISIN' else 0 if ts=='NON_A_VALIDER_ISIN' else None
    plan={'prix_signal_non_executable':round(price,4),'support_structurel':round(supports[0],4),
          'stop_technique_candidat':round(stop,4),'objectif_premiere_resistance':round(objective,4),
          'ratio_gain_risque_brut':round(rr,2),'atr14':round(atr,4),
          'quantite_theorique':None,'risque_estime_eur':None,'gain_net_estime_eur':None,
          'cout_achat_estime_eur':None,'ttf_estimee_eur':None,'courtages_aller_retour_estimes_eur':None,
          'methode':'Support/ATR et première résistance, sans confirmation graphique',
          'avertissement':'Pas de garantie stop, gap/slippage potentiellement supérieurs; courtage réel à contrôler'}
    # Fournit uniquement une quantité de simulation, aucune validation de taxe par ISIN.
    if tt is not None:
        entry=price*(1+slip);stop_fill=stop*(1-slip);target_fill=objective*(1-slip)
        unit=entry*(1+fb+tt)-stop_fill*(1-fb)
        available_risk=cfg['risque_par_position_eur']
        if cfg['positions_reelles_exhaustives_confirmees'] and cfg['positions_reelles']:
            used=sum(n(x.get('risque_theorique_eur')) or 0 for x in cfg['positions_reelles'])
            budget=sum(n(x.get('cout_achat_eur')) or 0 for x in cfg['positions_reelles'])
            available_risk=min(available_risk,max(0,cfg['risque_cumule_eur']-used))
            available_capital=max(0,cfg['capital_eur']-budget)
        else: available_capital=cfg['capital_eur']
        if unit>0:
            qty=max(0,min(math.floor((available_risk+1e-9)/unit),math.floor((available_capital+1e-9)/(entry*(1+fb+tt)))))
            gain=qty*(target_fill*(1-fb)-entry*(1+fb+tt))
            plan.update({'quantite_theorique':qty,'risque_estime_eur':round(qty*unit,2),
                'gain_net_estime_eur':round(gain,2),'cout_achat_estime_eur':round(qty*entry*(1+fb+tt),2),
                'ttf_estimee_eur':round(qty*entry*tt,2),
                'courtages_aller_retour_estimes_eur':round(qty*(entry*fb+target_fill*fb),2)})
            if qty==0:result['blocages'].append('QUANTITE_NULLE')
    result['plan_exploratoire']=plan
    return result

def generate():
    cfg=json.loads((CONF/'v88.json').read_text());tax=json.loads((CONF/'ttf_2026.json').read_text())
    if any(cfg[k]!=v for k,v in {'capital_eur':2000,'risque_par_position_eur':20,'risque_cumule_eur':60,
       'positions_max':3,'positions_par_secteur_max':2,'liquidite_min_eur':1000000,
       'frais_pct_par_ordre':0.35,'ratio_gain_risque_brut_min':2}.items()):raise ValueError('REGLE_RISQUE_MODIFIEE')
    v86=json.loads((DATA/'rapport_chatgpt_v86.json').read_text());v83=json.loads((DATA/'rapport_chatgpt_v83.json').read_text())
    if v86.get('schema_version')!='8.6' or v83.get('schema_version')!='8.3':raise ValueError('RAPPORT_INCOMPATIBLE')
    originals={x['ticker']:x for x in v83['univers']}
    annuals=json.loads((DATA/'fondamentaux_v86.json').read_text())['fiches']
    raw_technical=json.loads((DATA/'indicateurs.json').read_text())['indicateurs']
    # Au plus cinq dossiers approfondis : le top global, sans compléments supplémentaires.
    dossiers=[]
    for s in v86['top_5_global'][:5]:
        old=originals[s['ticker']]
        # Reprendre les niveaux 55 séances de V4, absents de l'export réduit V8.3.
        tech={**raw_technical.get(s['ticker'],{}),**old['indicateurs_techniques']}
        dossiers.append(plan(s['ticker'],tech,old,s,annuals.get(s['ticker']),cfg,tax))
    report={'schema_version':'8.8','genere_utc':datetime.now(timezone.utc).isoformat(),
       'source_v86':v86['genere_utc'],'dossiers':dossiers,'nombre_dossiers':len(dossiers),
       'positions_reelles':cfg['positions_reelles'] if cfg['positions_reelles_exhaustives_confirmees'] else [],
       'registre_exhaustif_confirme':cfg['positions_reelles_exhaustives_confirmees'],
       'achats_autorises':0,'mises_en_garde':['Top 5 recherche uniquement; plans non exécutables et non confirmés',
        'Frais, TTF indicative par ticker, niveaux et positionnement à confirmer manuellement',
        'Une absence de positions déclarées ne signifie pas que le portefeuille est vide']}
    (DATA/'rapport_chatgpt_v88.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False))
    print('V8.8:',len(dossiers),'dossiers, zéro achat autorisé')
    return report
if __name__=='__main__':generate()
