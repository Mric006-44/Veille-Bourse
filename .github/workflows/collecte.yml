"""Veille Bourse v2 : historiques et controles automatiques, sans signaux d'achat."""
import json
from datetime import datetime, timezone, date, timedelta
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

TICKERS = [
    'AC.PA','AI.PA','AIR.PA','ALO.PA','MT.AS','CS.PA','BNP.PA','EN.PA',
    'CAP.PA','CA.PA','ACA.PA','BN.PA','DSY.PA','EDEN.PA','ENGI.PA','EL.PA',
    'ERF.PA','RMS.PA','KER.PA','LR.PA','OR.PA','MC.PA','ML.PA','ORA.PA',
    'RI.PA','PUB.PA','RNO.PA','SAF.PA','SGO.PA','SAN.PA','SU.PA','GLE.PA',
    'STLAP.PA','STMPA.PA','TEP.PA','HO.PA','TTE.PA','URW.PA','VIE.PA','DG.PA',
]
OUT = Path('data')
HISTORY = OUT / 'historique'
HISTORY.mkdir(parents=True, exist_ok=True)


def number(x, places=4):
    try:
        v = float(x)
        return round(v, places) if np.isfinite(v) else None
    except (ValueError, TypeError):
        return None


def indicators(df):
    c, h, l, v = (df[k].astype(float) for k in ['Close', 'High', 'Low', 'Volume'])
    changes = c.diff()
    avg_gain = changes.clip(lower=0).ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    avg_loss = (-changes.clip(upper=0)).ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = (100 - 100/(1+rs)).mask((avg_loss == 0) & (avg_gain > 0), 100)
    rsi = rsi.mask((avg_gain == 0) & (avg_loss > 0), 0).mask((avg_gain == 0) & (avg_loss == 0), 50)
    m = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    sig = m.ewm(span=9, adjust=False).mean()
    tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    vm = v.rolling(20).mean()
    return {'date_seance': str(df.index[-1].date()), 'close':number(c.iloc[-1]),
            'volume':int(v.iloc[-1]), 'volume_moyen_20j':number(vm.iloc[-1]),
            'ratio_volume_20j':number(v.iloc[-1]/vm.iloc[-1]) if vm.iloc[-1] > 0 else None,
            'rsi14':number(rsi.iloc[-1],2), 'macd_12_26':number(m.iloc[-1]),
            'macd_signal9':number(sig.iloc[-1]), 'macd_histogramme':number((m-sig).iloc[-1]),
            'mm20':number(c.rolling(20).mean().iloc[-1]),
            'mm50':number(c.rolling(50).mean().iloc[-1]),
            'mm200':number(c.rolling(200).mean().iloc[-1]),
            'atr14':number(atr.iloc[-1]), 'seances':len(df)}


def checks(df):
    issues=[]
    required=['Open','High','Low','Close','Volume']
    if len(df)<210: issues.append('HISTORIQUE_INSUFFISANT')
    if df[required].isna().any().any(): issues.append('VALEUR_MANQUANTE')
    if (df[['Open','High','Low','Close']]<=0).any().any(): issues.append('COURS_NON_POSITIF')
    if (df['Volume']<0).any(): issues.append('VOLUME_NEGATIF')
    if ((df['High'] < df[['Open','Close','Low']].max(axis=1)) | (df['Low'] > df[['Open','Close','High']].min(axis=1))).any():
        issues.append('OHLC_INCOHERENT')
    if (df['Volume'].tail(5)==0).any(): issues.append('VOLUME_NUL_RECENT')
    # Les sauts de cours peuvent etre legitimes (OPA, resultats, dividendes) : verification manuelle.
    if (df['Close'].pct_change().abs().tail(30)>0.20).any(): issues.append('VARIATION_EXTREME_A_VERIFIER')
    # Week-ends et jours feries : tolere 4 jours calendaires, sans valider une cloture du jour.
    if (date.today()-df.index[-1].date()).days>4: issues.append('DONNEES_ANCIENNES')
    return issues


def main():
    results={}; errors={}; statuses={}
    for ticker in TICKERS:
        try:
            d=yf.download(ticker, period='2y', interval='1d', auto_adjust=False, progress=False, threads=False)
            if isinstance(d.columns, pd.MultiIndex): d.columns=d.columns.get_level_values(0)
            if d.empty: raise ValueError('Aucune donnee')
            d=d.sort_index()
            problems=checks(d)
            if len(d)<210: raise ValueError('Historique insuffisant')
            row=indicators(d)
            # Pas de deuxieme fournisseur : jamais VALIDE pour un ordre tactique.
            quality='REJETE' if any(p in problems for p in ['COURS_NON_POSITIF','OHLC_INCOHERENT','DONNEES_ANCIENNES','VALEUR_MANQUANTE','VOLUME_NEGATIF']) else 'A_VERIFIER'
            row['qualite']=quality; row['anomalies']=problems
            row['validation_independante']=False; row['autorise_signal_achat']=False
            row['source']='Yahoo Finance via yfinance'; row['prix_ajustes']=False
            d.index=d.index.strftime('%Y-%m-%d')
            d[['Open','High','Low','Close','Volume','Adj Close']].to_csv(HISTORY/f'{ticker}.csv',index_label='Date')
            results[ticker]=row; statuses[ticker]=quality
            print('OK',ticker,quality,problems)
        except Exception as ex:
            errors[ticker]=str(ex); statuses[ticker]='REJETE'
            print('ERREUR',ticker,ex)
    if not results: raise RuntimeError('Aucune donnee : fichiers precedents preserves')
    output={'schema_version':'2.0','mise_a_jour_utc':datetime.now(timezone.utc).isoformat(),
            'source':'Yahoo Finance via yfinance (non officiel, possiblement differe)',
            'univers':'Liste indicative de 40 valeurs; pas une composition CAC40 certifiee',
            'statuts':statuses,'indicateurs':results,'erreurs':errors,
            'politique':'Aucun signal d achat sans verification independante des cours et des historiques'}
    OUT.mkdir(exist_ok=True)
    (OUT/'indicateurs.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'FIN {len(results)} actions ; {len(errors)} erreurs')

if __name__=='__main__': main()
