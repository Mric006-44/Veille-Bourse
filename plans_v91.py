"""V9.1: exécute V8.8 puis retire le veto R/R du blocage, sans toucher aux coûts ni aux risques."""
import json
from pathlib import Path
from plans_v88 import generate
ROOT=Path(__file__).resolve().parent

def main():
    report=generate()
    for d in report.get('dossiers',[]):
        if 'RATIO_BRUT_INSUFFISANT' in d.get('blocages',[]):
            d['blocages'].remove('RATIO_BRUT_INSUFFISANT')
            d['notes'].append('R/R BRUT INFORMATIF: INFERIEUR A 2; NON ELIMINATOIRE; QUALITE DE LA THESE A CONTROLER')
        p=d.get('plan_exploratoire')
        if p is not None:
            p['ratio_gain_risque_non_eliminatoire']=p.get('ratio_gain_risque_brut')
        d['achat_autorise']=False
    report['ratio_gain_risque_filtre']=False
    report['achats_autorises']=0
    (ROOT/'data'/'rapport_chatgpt_v88.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False))
    print('V9.1 plans: ratio R/R conservé en information, jamais veto automatique')
    return report
if __name__=='__main__':main()
