"""V9.1: comite analytique, valorisation relative, pas de cible artificielle ni ordre."""
import json,math
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def num(v):
    try:
        v=float(v);return v if math.isfinite(v) else None
    except (ValueError,TypeError):return None

def evaluate(item,old,cat,sector_counts,plan88=None):
    ticker=item['ticker'];fund=old.get('indicateurs_fondamentaux',{}) if old else {}
    annual=item.get('indicateurs_pluriannuels') or {}
    rel=item.get('comparaison_sectorielle') or {}
    sector=item.get('secteur') or 'Inconnu';pe=num(fund.get('per_previsionnel'))
    ebitda=num(fund.get('ev_ebitda'))
    roic=num(annual.get('roic_pct'));fcfy=num(fund.get('fcf_yield_pct'))
    pe_rank=num(rel.get('per_percentile'));roic_rank=num(rel.get('roic_percentile'))
    peer_count=sector_counts.get(sector,0)
    judgement='INSUFFISANT'
    if peer_count>=5 and pe_rank is not None:
        judgement='DECOTE_RELATIVE_INDICATIVE' if pe_rank>=70 else ('CHER_RELATIVEMENT' if pe_rank<=30 else 'VALORISATION_INTERMEDIAIRE')
    catalyst=cat.get(ticker,[])
    timely=[x for x in catalyst if x['statut']=='DOCUMENTE_NON_VERIFIE_INDEPENDAMMENT']
    plan=item.get('plan_exploratoire_v73') or {}
    plan88=(plan88 or {}).get('plan_exploratoire') or {}
    blocks=list(item.get('blocages_achat') or [])
    blocks+=['CATALYSEUR_NON_VERIFIE_INDEPENDAMMENT' if timely else 'CATALYSEUR_ABSENT',
             'PEA_TTF_SPREAD_ET_SOURCE_A_CONTROLER','REGISTRE_POSITIONS_NON_CONFIRME']
    return {'ticker':ticker,'secteur':sector,'score_v86_100':item.get('score_global_v86_100'),
        'valorisation':{'per_previsionnel':pe,'ev_ebitda':ebitda,'fcf_yield_pct':fcfy,
          'roic_pct':roic,'per_percentile_sectoriel':pe_rank,'roic_percentile_sectoriel':roic_rank,
          'nb_comparables':peer_count,'interpretation':judgement,
          'limite':'Comparaison sectorielle Yahoo indicative; pas de multiple historique verifie'},
        'catalyseurs':catalyst,'catalyseur_documente':bool(timely),
        'objectif_unique_indicatif':plan88.get('objectif_premiere_resistance',plan.get('resistance_cible')), 
        'stop_candidat':plan88.get('stop_technique_candidat',plan.get('stop_invalidation_candidat')),
        'ratio_gain_risque_brut_informatif':plan88.get('ratio_gain_risque_brut'),
        'blocages':sorted(set(blocks)),'statut':'SURVEILLANCE','achat_autorise':False}

def create(v86,v83,cats,v88=None):
    if v86.get('schema_version')!='8.6' or v83.get('schema_version')!='8.3':raise ValueError('SOURCES_INCOMPATIBLES')
    old={x['ticker']:x for x in v83.get('univers',[])}
    counts={}
    for x in v86.get('univers',[]):
        s=x.get('secteur') or 'Inconnu';counts[s]=counts.get(s,0)+1
    v88plans={x['ticker']:x for x in (v88 or {}).get('dossiers',[])}
    selection=[evaluate(x,old.get(x['ticker']),cats.get('catalyseurs',{}),counts,v88plans.get(x['ticker'])) for x in v86['top_5_global'][:5]]
    return {'schema_version':'9.1','genere_utc':datetime.now(timezone.utc).isoformat(),
      'source_v86':v86.get('genere_utc'),'source_catalyseurs':cats.get('genere_utc'),
      'top_5_global':selection,'achats_autorises':0,
      'positions_reelles':'NON_CONFIRMEES','opportunites_non_executees':selection,
      'regles':['Ratio gain risque brut affiché mais jamais filtre eliminatoire','Un seul objectif technique indicatif, aucun scenario multiple',
                'Risque theorique par position 20 EUR, cumul 60 EUR, capital 2000 EUR',
                'Aucun achat sans verification PEA, couts, fiscalite, source independante, signal et registre'],
      'limites':['Aucune valorisation DCF ou cible prix sans hypothèses sourcées',
        'Catalyseurs non verifies automatiquement; URLs et dates a controler',
        'Les données sectorielles et états annuels ne sont pas des preuves de sous-valorisation']}

def main():
    data=ROOT/'data';v86=json.loads((data/'rapport_chatgpt_v86.json').read_text())
    v83=json.loads((data/'rapport_chatgpt_v83.json').read_text())
    cats=json.loads((data/'catalyseurs_v90.json').read_text())
    v88=json.loads((data/'rapport_chatgpt_v88.json').read_text())
    report=create(v86,v83,cats,v88)
    (data/'rapport_chatgpt_v91.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False))
    print('V9.1:',len(report['top_5_global']),'dossiers, aucun achat')
if __name__=='__main__':main()
