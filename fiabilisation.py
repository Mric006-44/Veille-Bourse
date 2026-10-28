"""V6.3: validation et audit des prix, historique long, aucune validation independante fictive."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import numpy as np

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data'
HIST=DATA/'historique_long'
CONF=ROOT/'config'/'fiabilisation.json'
WATCH=ROOT/'config'/'watchlist.json'
SRC=DATA/'indicateurs.json'
OUT=DATA/'fiabilisation.json'


def tickers():
    w=json.loads(WATCH.read_text(encoding='utf8'))
    return sorted(set(sum((w.get(k,[]) for k in ('cac40_indicatif','actions_supplementaires','etf')),[])))


def inspect(df, ref, cfg):
    issues=[]
    if isinstance(df.columns,pd.MultiIndex): df.columns=df.columns.get_level_values(0)
    needed=['Open','High','Low','Close','Volume','Adj Close']
    if df.empty or any(x not in df.columns for x in needed):
        raise ValueError('DONNEES_OU_COLONNES_ABSENTES')
    df=df.sort_index()
    if df.index.has_duplicates: issues.append('DATES_DUPLIQUEES')
    if df[needed].isna().any().any(): issues.append('DONNEES_MANQUANTES')
    if (df[['Open','High','Low','Close','Adj Close']]<=0).any().any(): issues.append('PRIX_NON_POSITIF')
    if (df['Volume']<0).any(): issues.append('VOLUME_NEGATIF')
    if ((df['High']<df[['Open','Close','Low']].max(axis=1)) | (df['Low']>df[['Open','Close','High']].min(axis=1))).any(): issues.append('OHLC_INCOHERENT')
    if len(df)<cfg['minimum_seances']: issues.append('HISTORIQUE_COURT')
    factor=df['Adj Close']/df['Close'].replace(0,np.nan)
    jumps=factor.div(factor.shift()).replace([np.inf,-np.inf],np.nan)
    # Only flags events, cannot label actual split/dividend without official actions.
    events=[{'date':str(dt.date()),'variation_facteur_pct':round(float((x-1)*100),3)}
        for dt,x in jumps.items() if pd.notna(x) and abs(x-1)>cfg['seuil_evenement_facteur_pct']/100]
    raw_gaps=(df['Open']/df['Close'].shift()-1).abs()
    adj_gaps=((df['Open']*factor)/(df['Close'].shift()*factor.shift())-1).abs()
    extreme=[str(d.date()) for d in df.index[(raw_gaps>cfg['seuil_gap_pct']/100) | (adj_gaps>cfg['seuil_gap_pct']/100)]]
    if extreme: issues.append('GAP_EXTREME_A_EXAMINER')
    last_date=str(df.index[-1].date())
    delta=None
    if ref and ref.get('date_seance')==last_date and ref.get('close'):
        delta=round(100*(float(df['Close'].iloc[-1])/float(ref['close'])-1),4)
        if abs(delta)>cfg['tolerance_comparaison_interne_pct']: issues.append('ECART_CLOTURE_V4')
    else: issues.append('DATE_V4_NON_ALIGNEE')
    return df, {'date_derniere_seance':last_date,'seances':len(df),
        'close':round(float(df['Close'].iloc[-1]),4),'ecart_v4_pct':delta,
        'evenements_facteur_ajustement':events[-30:], 'nombre_evenements_facteur':len(events),
        'gaps_extremes':extreme[-20:], 'anomalies':issues,
        'statut':'A_EXAMINER' if issues else 'CONTROLES_INTERNES_OK',
        'validation_independante':False,'autorise_signal_achat':False,
        'note':'Comparaison avec V4 issue de la meme source Yahoo: PAS independante.'}


def main():
    import yfinance as yf
    cfg=json.loads(CONF.read_text(encoding='utf8'))
    v4=json.loads(SRC.read_text(encoding='utf8'))
    HIST.mkdir(parents=True,exist_ok=True)
    results={}; errors={}
    for t in tickers():
        try:
            df=yf.download(t,period=cfg['periode_yahoo'],interval='1d',auto_adjust=False,progress=False,threads=False)
            df,record=inspect(df,v4.get('indicateurs',{}).get(t),cfg)
            if 'DONNEES_MANQUANTES' not in record['anomalies'] and 'PRIX_NON_POSITIF' not in record['anomalies']:
                export=df.copy(); export.index=export.index.strftime('%Y-%m-%d')
                export[['Open','High','Low','Close','Volume','Adj Close']].to_csv(HIST/f'{t}.csv',index_label='Date')
            results[t]=record
            print('V6.3',t,record['statut'])
        except Exception as e:
            errors[t]=str(e)[:200]
            print('V6.3 ERROR',t,str(e)[:150])
    if not results: raise RuntimeError('Pas de resultats: audit non publie')
    DATA.mkdir(parents=True,exist_ok=True)
    doc={'schema_version':'6.3','genere_utc':datetime.now(timezone.utc).isoformat(),
         'source':'Yahoo Finance via yfinance (source unique)',
         'historique_demande':cfg['periode_yahoo'],'titres_configures':len(tickers()),
         'titres_audites':len(results),'titres_en_erreur':len(errors),'titres':results,'erreurs':errors,
         'verification_independante':'NON_DISPONIBLE', 'achats_autorises':0,
         'limites':['Une autre interrogation Yahoo ne constitue pas une seconde source',
           'Facteurs Adj Close non suffisants pour identifier de facon certaine dividendes ou splits',
           'Historique long ne corrige pas automatiquement le biais de survivance des backtests',
           'Les anciens backtests continuent de travailler sur data/historique (2 ans)']}
    OUT.write_text(json.dumps(doc,ensure_ascii=False,indent=2),encoding='utf8')
    print('V6.3',len(results),'audites',len(errors),'erreurs')

if __name__=='__main__':main()
