"""V8: enrichissement des cinq dossiers V7.3 sans changer leur selection."""
import json
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parent; DATA=ROOT/'data'
def load(name): return json.loads((DATA/name).read_text(encoding='utf8'))
def create(technical,fundamentals):
 if str(technical.get('schema_version'))!='7.3' or str(fundamentals.get('schema_version'))!='8.0':
  raise ValueError('Versions V7.3 / V8 incompatibles')
 fiches=fundamentals.get('fiches',{})
 merged=[]
 for t in technical.get('top_5_dossiers',[]):
  ticker=t['ticker']; f=fiches.get(ticker)
  merged.append({'ticker':ticker,'analyse_technique':t,'analyse_fondamentale':f,
   'donnees_fondamentales_manquantes':(f['evaluation']['criteres_non_evaluables'] if f else ['FICHE_ENTIERE']),
   'reserves':['DONNEES_YAHOO_NON_RECROISEES_AVEC_RAPPORTS_FINANCIERS','AUCUN_ACHAT_AUTORISE']})
 return {'schema_version':'8.0','genere_utc':datetime.now(timezone.utc).isoformat(),
  'date_source_technique':technical.get('genere_utc'),'date_source_fondamentale':fundamentals.get('genere_utc'),
  'regles_tactiques_v73':technical.get('regles'), 'nombre_dossiers':len(merged),
  'dossiers':merged,'erreurs_fondamentales':fundamentals.get('erreurs',{}),
  'politique':'Classement V7.3 conserve; fondamentaux non utilises pour authoriser un achat ni reclasser sans validation.',
  'achats_autorises':0}
def main():
 out=create(load('rapport_chatgpt_v73.json'),load('fondamentaux_v8.json'))
 (DATA/'rapport_chatgpt_v8.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
 print('V8 rapport ChatGPT:',out['nombre_dossiers'],'dossiers, zero achat autorise')
if __name__=='__main__': main()
