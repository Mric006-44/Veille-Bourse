"""V8: collecte des fondamentaux Yahoo, sans signal d'achat. Donnees non auditees."""
import json, math, time
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data'; CONFIG=ROOT/'config'
FIELDS={
 'identite':['longName','shortName','sector','industry','country','currency','financialCurrency','quoteType','marketCap','sharesOutstanding'],
 'valorisation':['trailingPE','forwardPE','priceToBook','enterpriseToEbitda','enterpriseToRevenue','trailingEps','forwardEps','priceToSalesTrailing12Months'],
 'croissance':['revenueGrowth','earningsGrowth','earningsQuarterlyGrowth'],
 'rentabilite':['profitMargins','operatingMargins','grossMargins','returnOnEquity','returnOnAssets'],
 'solidite':['totalDebt','totalCash','debtToEquity','currentRatio','quickRatio','freeCashflow','operatingCashflow'],
 'actionnaire':['dividendYield','dividendRate','payoutRatio'],
 'estimations':['targetMeanPrice','targetLowPrice','targetHighPrice','numberOfAnalystOpinions','recommendationMean']}
INDUSTRY_FINANCIAL=('Financial Services','Financials')
def clean(v):
 if isinstance(v,bool): return v
 if isinstance(v,(str,int)): return v
 if isinstance(v,float): return round(v,8) if math.isfinite(v) else None
 return None
def ratio(numerateur, denominateur):
    if numerateur is None or denominateur is None:
        return None
    if denominateur <= 0:
        return None
    return numerateur / denominateur

def ratios_complementaires(info):
    dette = info.get("totalDebt")
    tresorerie = info.get("totalCash")
    fcf = info.get("freeCashflow")
    capitalisation = info.get("marketCap")
    ca = info.get("totalRevenue")

    return {
        "dette_nette": (
            dette - tresorerie
            if dette is not None and tresorerie is not None
            else None
        ),
        "fcf_yield_pct": (
            100 * ratio(fcf, capitalisation)
            if fcf is not None else None
        ),
        "marge_fcf_pct": (
            100 * ratio(fcf, ca)
            if fcf is not None else None
        )
    }
 
def extract(info):
 return {section:{k:clean(info.get(k)) for k in keys} for section,keys in FIELDS.items()}

def evaluate(record):
 d=record['donnees']; identity=d['identite']; financial=identity['sector'] in INDUSTRY_FINANCIAL
 # Score purement descriptif; ne pas imputer les indicateurs absents.
 rules=[('PER_TTM_POSITIF',d['valorisation']['trailingPE'],lambda x:0<x<=25,10),
 ('PER_FORWARD_POSITIF',d['valorisation']['forwardPE'],lambda x:0<x<=22,10),
 ('CROISSANCE_CA_POSITIVE',d['croissance']['revenueGrowth'],lambda x:x>0,15),
 ('CROISSANCE_BPA_POSITIVE',d['croissance']['earningsGrowth'],lambda x:x>0,10),
 ('ROE_SUP_10',d['rentabilite']['returnOnEquity'],lambda x:x>=.10,15),
 ('MARGE_OPERATIONNELLE_SUP_10',d['rentabilite']['operatingMargins'],lambda x:x>=.10,15),
 ('MARGE_NETTE_POSITIVE',d['rentabilite']['profitMargins'],lambda x:x>0,10),
 ('FCF_POSITIF',d['solidite']['freeCashflow'],lambda x:x>0,15)]
 # Cashflows / D/E non comparables pour les banques et assurances.
 if financial: rules=[r for r in rules if r[0] not in ('FCF_POSITIF','MARGE_OPERATIONNELLE_SUP_10')]
 available=[];unavailable=[];achieved=[];max_score=0;points=0
 for name,val,predicate,weight in rules:
  if isinstance(val,(float,int)) and not isinstance(val,bool) and math.isfinite(val):
   available.append(name);max_score+=weight
   if predicate(val): points+=weight;achieved.append(name)
  else: unavailable.append(name)
 coverage=round(100*max_score/sum(x[3] for x in rules),1)
 score=round(points/max_score*100,1) if max_score else None
 return {'score_observe_sur_indicateurs_disponibles_100':score,'couverture_score_pct':coverage,
         'criteres_positifs':achieved,'criteres_non_evaluables':unavailable,
         'comparable_avec_secteur_financier':not financial,
         'decision':'ANALYSE_INCOMPLETE' if coverage<60 else 'EXPLORATOIRE_NON_VALIDE'}

def run(fetch=None, pause=0):
 if fetch is None:
  import yfinance as yf
  fetch=lambda ticker: yf.Ticker(ticker).info
 watch=json.loads((CONFIG/'watchlist.json').read_text(encoding='utf8'))
 cfg=json.loads((CONFIG/'fondamentaux_v8.json').read_text(encoding='utf8'))
 tickers=list(dict.fromkeys(t for g in ('cac40_indicatif','actions_supplementaires','etf') for t in watch.get(g,[])))
 results={};errors={}
 for ticker in tickers:
  try:
   raw=fetch(ticker)
   if not isinstance(raw,dict) or not raw.get('longName') and not raw.get('shortName'):
    raise ValueError('IDENTITE_NON_DISPONIBLE')
   data=extract(raw)
   record={'ticker':ticker,'donnees':data,'evaluation':None,
           'source':'Yahoo Finance / yfinance .info','date_collecte_utc':datetime.now(timezone.utc).isoformat(),
           'periode_comptable':'NON_CERTIFIEE','date_publication_financiere':'NON_DISPONIBLE',
           'valide_par_document_primaire':False,'achat_autorise':False}
   record['evaluation']=evaluate(record)
   results[ticker]=record
  except Exception as e:
   errors[ticker]=str(e)[:180]
  if pause: time.sleep(pause)
 out={'schema_version':'8.0','genere_utc':datetime.now(timezone.utc).isoformat(),
      'univers_configure':len(tickers),'fiches_disponibles':len(results),'erreurs':errors,
      'fiches':results,'source_unique':'Yahoo Finance / yfinance .info',
      'mise_en_garde':'Ratios indicatifs; periodes, devises, consolidation et millesimes non certifies. Ne pas comparer aveuglement banques/industries. Aucun conseil achat.',
      'achats_autorises':0}
 DATA.mkdir(exist_ok=True)
 (DATA/'fondamentaux_v8.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
 print(f'V8 fondamentaux: {len(results)}/{len(tickers)} fiches, {len(errors)} erreurs')
 return out
if __name__=='__main__':
 cfg=json.loads((CONFIG/'fondamentaux_v8.json').read_text(encoding='utf8'))
 run(pause=cfg.get('pause_secondes',0))
