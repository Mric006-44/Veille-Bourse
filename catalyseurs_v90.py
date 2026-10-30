"""V9.0: validation de catalyseurs explicitement sourcés, pas de scraping ni d'invention."""
import json
from datetime import date, datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def validate(items, asof=None):
    asof=asof or date.today();result={}; errors=[]
    for i,row in enumerate(items):
        try:
            t=row['ticker'];event=row['evenement'];url=row['url_source'];origin=row['source']
            published=date.fromisoformat(row['date_publication']); recheck=date.fromisoformat(row['date_reexamen'])
            if not(t and event and origin and url.startswith('https://') and published<=asof and recheck>=published):raise ValueError('CHAMPS_OU_DATES_INVALIDES')
            status='A_REEXAMINER' if recheck<asof else 'DOCUMENTE_NON_VERIFIE_INDEPENDAMMENT'
            result.setdefault(t,[]).append({'evenement':event,'source':origin,'url_source':url,
                'date_publication':str(published),'date_reexamen':str(recheck),
                'statut':status,'impact_attendu':row.get('impact_attendu'),
                'risque_associe':row.get('risque_associe')})
        except (KeyError,TypeError,ValueError,AttributeError) as e:errors.append({'ligne':i,'erreur':str(e)})
    return result,errors

def main():
    raw=json.loads((ROOT/'config'/'catalyseurs_v90.json').read_text(encoding='utf8'))
    items,errors=validate(raw['evenements'])
    doc={'schema_version':'9.0','genere_utc':datetime.now(timezone.utc).isoformat(),'catalyseurs':items,
      'rejets':errors,'nb_documents':sum(map(len,items.values())),'avertissement':'URL fournie, contenu non authentifie automatiquement; pas de catalyseur invente'}
    (ROOT/'data'/'catalyseurs_v90.json').write_text(json.dumps(doc,indent=2,ensure_ascii=False))
    print('V9.0:',doc['nb_documents'],'catalyseurs documentes; refus:',len(errors))
if __name__=='__main__':main()
