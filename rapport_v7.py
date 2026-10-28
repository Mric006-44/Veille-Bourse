"""V7: daily decision-support report, no order/permission to buy."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter

ROOT=Path(__file__).resolve().parent
D=ROOT/'data'
CFG=ROOT/'config'/'rapport_v7.json'


def read(path):
    return json.loads(path.read_text(encoding='utf8')) if path.exists() else None


def report(v4, v5, audit, previous, cfg):
    if v4.get('schema_version')!='4.0' or v5.get('schema_version')!='5.0':
        raise ValueError('Versions des donnees V4/V5 incompatibles')
    if v5.get('source_v4')!=v4.get('mise_a_jour_utc'):
        raise ValueError('Screening V5 non aligne sur collecte V4')
    entries={x['ticker']:x for x in v5['univers']}
    prev={x['ticker']:x for x in (previous or {}).get('univers',[])}
    seen={}; changes=[]; rejected=[]; flags=Counter(); rankings=[]
    for t,s in sorted(v4['indicateurs'].items()):
        e=entries.get(t)
        if not e: continue
        qa=(audit or {}).get('titres',{}).get(t,{})
        anomalies=list(dict.fromkeys(s.get('anomalies',[])+qa.get('anomalies',[])))
        reasons=set(e.get('blocages',[]))
        if qa.get('validation_independante') is not True: reasons.add('PAS_DE_SOURCE_INDEPENDANTE')
        if not qa: reasons.add('AUDIT_HISTORIQUE_ABSENT')
        if anomalies: reasons.add('ANOMALIE_A_EXAMINER')
        if s.get('qualite')!='A_VERIFIER': reasons.add('QUALITE_SOURCE_INATTENDUE')
        if s.get('valeur_echangee_moyenne20_eur_estimee') is None or s.get('valeur_echangee_moyenne20_eur_estimee',0)<cfg['seuil_liquidite_eur']:
            reasons.add('LIQUIDITE_INSUFFISANTE')
        p=prev.get(t)
        current=set(e.get('configurations',[]))
        old=set(p.get('configurations',[])) if p else set()
        if p and (current!=old or abs(e.get('score_exploratoire_100',0)-p.get('score_exploratoire_100',0))>=cfg['changement_score_min']):
            changes.append({'ticker':t,'score_precedent':p.get('score_exploratoire_100'),
                'score_actuel':e.get('score_exploratoire_100'),
                'nouvelles_configurations':sorted(current-old),'configurations_disparues':sorted(old-current)})
        flags.update(current)
        item={'ticker':t,'date_seance':s.get('date_seance'),'close':s.get('close'),
            'score_exploratoire_100':e.get('score_exploratoire_100'),
            'configurations':sorted(current),'rsi14':s.get('rsi14'),'adx14':s.get('adx14'),
            'macd_histogramme':s.get('macd_histogramme'),
            'force_relative_cac40_20j_pct':s.get('force_relative_cac40_20j_pct'),
            'performance_20j_pct':s.get('performance_20j_pct'),
            'volume_ratio':s.get('ratio_volume_20j'),
            'liquidite_moyenne_eur':s.get('valeur_echangee_moyenne20_eur_estimee'),
            'qualite_v4':s.get('qualite'),'audit_historique':qa.get('statut','ABSENT'),
            'anomalies':anomalies,'blocages':sorted(reasons),
            'validation_independante':False,'autorise_signal_achat':False}
        seen[t]=item
        if 'LIQUIDITE_INSUFFISANTE' in reasons or anomalies: rejected.append(item)
        elif current: rankings.append(item)
    rankings.sort(key=lambda x:(-x['score_exploratoire_100'],x['ticker']))
    changes.sort(key=lambda x: (-abs(x['score_actuel']-(x['score_precedent'] or 0)),x['ticker']))
    by_strategy={k:[e for e in rankings if k in e['configurations']][:cfg['max_par_strategie']]
         for k in ('TENDANCE','REBOND_POTENTIEL','CASSURE')}
    top=rankings[:cfg['max_dossiers']]
    return {'schema_version':'7.0','genere_utc':datetime.now(timezone.utc).isoformat(),
       'source_v4':v4['mise_a_jour_utc'],'source_v5':v5['genere_utc'],
       'source_audit_v63':(audit or {}).get('genere_utc'),
       'compteurs':{'titres_analyses':len(seen),'dossiers_a_etudier':len(rankings),
           'anomalies_ou_illiquides':len(rejected),'configurations':dict(flags),
           'changements_detectes':len(changes)},
       'top_dossiers_a_approfondir':top,'par_strategie':by_strategy,
       'changements_depuis_rapport_precedent':changes[:cfg['max_changements']],
       'exclusions_et_alertes':rejected,
       'univers':list(seen.values()),'achats_autorises':0,
       'avertissement':'EXPLORATOIRE. Source Yahoo non independamment validee. Aucun ordre ni signal achat autorise. Les scores ne sont pas predictifs.'}


def main():
    cfg=read(CFG);v4=read(D/'indicateurs.json');v5=read(D/'screening.json')
    if not cfg or not v4 or not v5: raise RuntimeError('Donnees ou configuration absentes')
    audit=read(D/'fiabilisation.json')
    previous=read(D/'rapport_veille.json')
    result=report(v4,v5,audit,previous,cfg)
    (D/'rapport_veille.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    # Lightweight report for ChatGPT, public data only.
    slim={k:result[k] for k in ['schema_version','genere_utc','source_v4','source_audit_v63','compteurs',
           'top_dossiers_a_approfondir','changements_depuis_rapport_precedent','avertissement','achats_autorises']}
    (D/'rapport_chatgpt.json').write_text(json.dumps(slim,ensure_ascii=False,indent=2),encoding='utf8')
    print('V7:',result['compteurs'],'0 achats autorises')

if __name__=='__main__':main()
