"""Veille-Bourse V5: classement exploratoire, JAMAIS d'ordres ni d'achats autorises.
Lit le JSON V4 et produit data/screening.json, sans modifier collecte.py.
"""
from __future__ import annotations
import json
import math
from datetime import datetime, timezone, date
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
INPUT = ROOT / 'data' / 'indicateurs.json'
CONFIG = ROOT / 'config' / 'screening.json'
OUTPUT = ROOT / 'data' / 'screening.json'


def number(x):
    try:
        z = float(x)
        return z if math.isfinite(z) else None
    except (ValueError, TypeError):
        return None


def meets(s, conditions):
    return all(number(s.get(k)) is not None and op(number(s[k]), v) for k, op, v in conditions)


def gt(a,b): return a > b

def lt(a,b): return a < b


def score(s):
    """Score heuristique descriptif, non backteste, pas une probabilite de gain."""
    pts = 0
    checks = [
        (number(s.get('close')) is not None and number(s.get('mm200')) is not None and s['close'] > s['mm200'], 12),
        (number(s.get('mm50')) is not None and number(s.get('mm200')) is not None and s['mm50'] > s['mm200'], 10),
        (number(s.get('adx14')) is not None and s['adx14'] >= 20, 10),
        (number(s.get('di_plus14')) is not None and number(s.get('di_moins14')) is not None and s['di_plus14'] > s['di_moins14'], 8),
        (number(s.get('rsi14')) is not None and 45 <= s['rsi14'] <= 70, 10),
        (number(s.get('macd_histogramme')) is not None and s['macd_histogramme'] > 0, 10),
        (number(s.get('force_relative_cac40_20j_pct')) is not None and s['force_relative_cac40_20j_pct'] > 0, 10),
        (number(s.get('performance_20j_pct')) is not None and s['performance_20j_pct'] > 0, 10),
        (number(s.get('ratio_volume_20j')) is not None and s['ratio_volume_20j'] >= 1, 10),
        (number(s.get('pente_mm20_5j_pct')) is not None and s['pente_mm20_5j_pct'] > 0, 10),
    ]
    return sum(n for matched,n in checks if matched)


def strategies(s,cfg):
    p = number(s.get('close')); ma50=number(s.get('mm50')); ma200=number(s.get('mm200'))
    adx=number(s.get('adx14')); pos=number(s.get('di_plus14')); neg=number(s.get('di_moins14'))
    rsi=number(s.get('rsi14')); hist=number(s.get('macd_histogramme'))
    vol=number(s.get('ratio_volume_20j')); high20=number(s.get('plus_haut_20j_precedent'))
    low20=number(s.get('plus_bas_20j_precedent')); atr=number(s.get('atr14'))
    ret20=number(s.get('performance_20j_pct')); rel=number(s.get('force_relative_cac40_20j_pct'))
    flags=[]
    if all(x is not None for x in (p,ma50,ma200,adx,pos,neg,rsi,hist,rel)):
        if p>ma50>ma200 and adx>=20 and pos>neg and 45<=rsi<=70 and hist>0 and rel>0:
            flags.append('TENDANCE')
    if all(x is not None for x in (p,ma50,rsi,hist,low20,atr)) and atr>0:
        # Configuration potentielle de rebond, non confirmation temporelle du croisement
        if abs(p-ma50)<=atr and 35<=rsi<=55 and hist>0 and p>low20:
            flags.append('REBOND_POTENTIEL')
    if all(x is not None for x in (p,high20,vol,rsi,ret20,rel)):
        if p>high20 and vol>=cfg['volume_relatif_min_cassure'] and 50<=rsi<=80 and ret20>0 and rel>0:
            flags.append('CASSURE')
    return flags


def risk_example(s,cfg):
    """Hypothese purement pedagogique, pas de cours executable ni d'ordre."""
    entry=number(s.get('close')); atr=number(s.get('atr14'))
    if entry is None or atr is None or entry<=0 or atr<=0: return None
    stop=entry-cfg['perte_stop_atr_multiple']*atr
    if stop<=0: return None
    fb=cfg['frais_achat_pct']/100; fs=cfg['frais_vente_pct']/100
    unit=entry*(1+fb)-stop*(1-fs)
    qty=max(0,math.floor(cfg['risque_max_position_eur']/unit)) if unit>0 else 0
    return {'prix_entree_hypothetique':round(entry,4),'stop_hypothetique':round(stop,4),
            'risque_par_action_frais_inclus':round(unit,4),'quantite_theorique_max':qty,
            'risque_theorique_total_eur':round(qty*unit,2),
            'capital_estime_frais_achat_inclus_eur':round(qty*entry*(1+fb),2),
            'limites':'Hors spread, slippage, gaps, contraintes courtier et liquidite; le stop n est jamais garanti'}


def main():
    cfg=json.loads(CONFIG.read_text(encoding='utf-8'))
    v4=json.loads(INPUT.read_text(encoding='utf-8'))
    if str(v4.get('schema_version'))!='4.0':
        raise RuntimeError('V5 exige les donnees V4.0. Aucun resultat publie.')
    if not isinstance(v4.get('indicateurs'),dict) or not v4['indicateurs']:
        raise RuntimeError('Aucun titre dans les donnees V4')
    today=datetime.now(ZoneInfo('Europe/Paris')).date()
    universe=[]; selections={'TENDANCE':[],'REBOND_POTENTIEL':[],'CASSURE':[]}
    for ticker,s in sorted(v4['indicateurs'].items()):
        reasons=[]
        if s.get('qualite')=='REJETE': reasons.append('QUALITE_REJETEE')
        if s.get('qualite')!='A_VERIFIER': reasons.append('STATUT_SOURCE_INATTENDU')
        if s.get('validation_independante') is not True: reasons.append('PAS_DE_SECONDE_SOURCE')
        if not s.get('date_seance'): reasons.append('DATE_ABSENTE')
        else:
            try:
                age=(today-date.fromisoformat(s['date_seance'])).days
                if age<0 or age>cfg['cours_max_age_jours']: reasons.append('DONNEES_PERIMEES')
            except ValueError: reasons.append('DATE_INVALIDE')
        amount=number(s.get('valeur_echangee_moyenne20_eur_estimee'))
        if amount is None or amount<cfg['valeur_echangee_min_20j_eur']: reasons.append('LIQUIDITE_INSUFFISANTE')
        if number(s.get('seances_volume_nul_20j')) is None or s['seances_volume_nul_20j']>0: reasons.append('VOLUME_NUL_20J')
        if s.get('anomalies'): reasons.append('ANOMALIES_DONNEES')
        if not cfg.get('univers_eligible_pea_verifie',False): reasons.append('ELIGIBILITE_PEA_NON_VERIFIEE')
        if cfg.get('positions_ouvertes_risque_cumule_eur') is None: reasons.append('RISQUE_CUMULE_INCONNU')
        if cfg.get('capital_disponible_eur') is None: reasons.append('CAPITAL_DISPONIBLE_INCONNU')
        flags=strategies(s,cfg)
        # La fiabilite du fournisseur et les controles du carnet sont des prealables
        # inconditionnels. Aucune proposition d'achat automatique.
        entry={'ticker':ticker,'date_seance':s.get('date_seance'),'score_exploratoire_100':score(s),
               'configurations':flags,'qualite_v4':s.get('qualite'),'validation_independante':False,
               'eligible_pour_achat':False,'verdict':'EXCLU_LIQUIDITE' if 'LIQUIDITE_INSUFFISANTE' in reasons else ('A_ETUDIER' if flags else 'SURVEILLANCE'),
               'blocages':sorted(set(reasons+['PAS_DE_VERIFICATION_SPREAD_ET_CARNET'])),
               'exemple_risque':risk_example(s,cfg) if flags else None}
        universe.append(entry)
        if flags and 'LIQUIDITE_INSUFFISANTE' not in reasons and 'ANOMALIES_DONNEES' not in reasons:
            for flag in flags: selections[flag].append(entry)
    for k in selections:
        selections[k]=sorted(selections[k],key=lambda x:(-x['score_exploratoire_100'],x['ticker']))[:cfg['max_suggestions_par_strategie']]
    output={'schema_version':'5.0','genere_utc':datetime.now(timezone.utc).isoformat(),
            'source_v4':v4.get('mise_a_jour_utc'),'titres_analyses':len(universe),
            'hypotheses':cfg,'selections_exploratoires':selections,'univers':universe,
            'nombre_achats_autorises':0,
            'avertissement':'AUCUN ORDRE AUTORISE. Score non backteste. Donnees source unique, prix non executables; gap et spread inconnus.'}
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT.write_text(json.dumps(output,indent=2,ensure_ascii=False),encoding='utf-8')
    print('V5: ',len(universe),'titres,',sum(len(v) for v in selections.values()),'configurations affichees, zero achat autorise')

if __name__=='__main__': main()
