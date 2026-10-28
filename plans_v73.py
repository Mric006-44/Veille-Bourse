"""V7.3: shortlist exploratoire de 5 dossiers; AUCUN ordre ni autorisation d'achat.
Lit les sorties V4/V5/V6.3 et n'ajuste aucun historique ni cours.
"""
from __future__ import annotations
import json
import math
from datetime import datetime, timezone, date
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
CONFIG = ROOT / 'config'


def load(p):
    return json.loads(p.read_text(encoding='utf-8'))


def num(x):
    try:
        z = float(x)
        return z if math.isfinite(z) else None
    except (TypeError, ValueError):
        return None


def amount(q, p, pct):
    return q * p * pct / 100


def ttf_status(ticker, tax):
    if ticker in tax['oui'] and ticker in tax['non']:
        raise ValueError('TTF contradictoire: ' + ticker)
    if ticker in tax['oui']:
        return 'OUI'
    if ticker in tax['non']:
        return 'NON'
    return 'A_VERIFIER'


def build_plan(s, settings, tax_status, tax):
    """Possible structural levels. Cannot confirm manual chart zones or executable order prices."""
    missing = []
    keys = ('close','atr14','plus_bas_20j_precedent','plus_bas_55j_precedent',
            'plus_haut_20j_precedent','plus_haut_55j_precedent','mm20','mm50','mm200')
    for key in keys:
        if num(s.get(key)) is None:
            missing.append(key)
    if missing:
        return None, missing, ['DONNEES_TECHNIQUES_MANQUANTES']
    p = num(s['close']); atr = num(s['atr14'])
    if p <= 0 or atr <= 0:
        return None, [], ['COURS_OU_ATR_INVALIDE']
    supports = sorted(set([num(s['plus_bas_20j_precedent']),num(s['plus_bas_55j_precedent']),
                           num(s['mm20']),num(s['mm50']),num(s['mm200'])]),reverse=True)
    resistances = sorted(set([num(s['plus_haut_20j_precedent']),num(s['plus_haut_55j_precedent'])]))
    below = [x for x in supports if 0 < x < p]
    above = [x for x in resistances if x > p]
    if not below:
        return None, [], ['AUCUN_SUPPORT_SOUS_LE_COURS']
    if not above:
        return None, [], ['AUCUNE_RESISTANCE_AU_DESSUS_DU_COURS']
    support = below[0] # closest lower structural candidate
    target = above[0] # first historical barrier above price
    stop = support - settings['marge_invalidation_atr'] * atr
    if stop <= 0 or stop >= p:
        return None, [], ['INVALIDATION_NON_EXPLOITABLE']
    fee_buy = settings['frais_achat_pct']/100
    fee_sell = settings['frais_vente_pct']/100
    slip = settings['slippage_hypothese_pct_par_cote']/100
    tax_rate = tax['taux_pct']/100 if tax_status == 'OUI' else (0 if tax_status == 'NON' else None)
    if tax_rate is None:
        return {'support_candidat':round(support,4),'resistance_cible':round(target,4),
                'stop_invalidation_candidat':round(stop,4),'quantite_theorique':None}, ['statut_ttf'], ['TTF_INDETERMINEE']
    entry = p*(1+slip)
    stop_fill = stop*(1-slip)
    target_fill = target*(1-slip)
    per_unit_risk = entry*(1+fee_buy+tax_rate)-stop_fill*(1-fee_sell)
    per_unit_gain = target_fill*(1-fee_sell)-entry*(1+fee_buy+tax_rate)
    if per_unit_risk <= 0:
        return None, [], ['RISQUE_PAR_TITRE_INVALIDE']
    price_cap = entry*(1+fee_buy+tax_rate)
    qty = max(0,min(math.floor((settings['risque_max_position_eur']+1e-10)/per_unit_risk),
                    math.floor((settings['budget_tactique_total_eur']+1e-10)/price_cap)))
    rr = per_unit_gain / per_unit_risk
    plan = {'prix_signal_non_executable':round(p,4),'support_candidat':round(support,4),
            'invalidation_justification':'Sous support/moyenne mobile candidate avec marge de volatilite; confirmation graphique requise',
            'stop_invalidation_candidat':round(stop,4),'resistance_cible':round(target,4),
            'objectif_justification':'Premiere resistance historique (20/55 seances) au-dessus du cours',
            'atr14':round(atr,4),'ratio_gain_risque_net_estime':round(rr,2),
            'quantite_theorique_max':qty,'risque_total_eur_estime':round(qty*per_unit_risk,2),
            'gain_potentiel_eur_estime':round(qty*per_unit_gain,2),
            'capital_avec_frais_et_ttf_eur_estime':round(qty*price_cap,2),
            'courtages_aller_retour_eur_estimes':round(qty*(entry*fee_buy+target_fill*fee_sell),2),
            'ttf_achat_eur_estimee':round(qty*entry*tax_rate,2),
            'hypothese_slippage_pct_par_cote':settings['slippage_hypothese_pct_par_cote'],
            'risque_non_garanti':'Gaps, spread reel, fiscalite, frais minimums et execution peuvent modifier la perte'}
    reasons=[]
    if rr < settings['ratio_gain_risque_min']:
        reasons.append('RATIO_GAIN_RISQUE_INSUFFISANT')
    if qty < 1:
        reasons.append('QUANTITE_NULLE')
    return plan, [], reasons


def generate(v4,v5,audit,cfg,tax,now=None):
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(ZoneInfo('Europe/Paris')).date()
    if str(v4.get('schema_version')) != '4.0' or str(v5.get('schema_version')) != '5.0':
        raise ValueError('Versions entree V4/V5 inattendues')
    if str(audit.get('schema_version')) != '6.3':
        raise ValueError('Audit V6.3 absent')
    if not (v4.get('mise_a_jour_utc') == v5.get('source_v4')):
        raise ValueError('Screening V5 non aligne avec collecte V4')
    if audit.get('titres_audites',0) < 1:
        raise ValueError('Audit vide')
    universe = []
    ranking = {x['ticker']:x for x in v5.get('univers',[])}
    audit_tickers = audit.get('titres',{})
    for ticker,s in sorted(v4.get('indicateurs',{}).items()):
        base = ranking.get(ticker,{})
        a = audit_tickers.get(ticker,{})
        blockers = set(base.get('blocages',[]))
        missing = []
        age = None
        try:
            age = (today-date.fromisoformat(s['date_seance'])).days
        except (KeyError,ValueError,TypeError):
            blockers.add('DATE_INVALIDE')
        if age is None or not 0 <= age <= cfg['cours_age_max_jours']:
            blockers.add('DONNEES_PERIMEES')
        liquidity = num(s.get('valeur_echangee_moyenne20_eur_estimee'))
        if liquidity is None:
            missing.append('valeur_echangee_moyenne20_eur_estimee')
        if liquidity is None or liquidity < cfg['liquidite_min_eur_jour']:
            blockers.add('LIQUIDITE_INFERIEURE_1M')
        if a.get('statut') != 'CONTROLES_INTERNES_OK':
            blockers.add('AUDIT_HISTORIQUE_NON_CONFORME')
        if not s.get('validation_independante',False):
            blockers.add('PAS_DE_SOURCE_INDEPENDANTE')
        status = ttf_status(ticker,tax)
        plan, unavailable, plan_blockers = build_plan(s,cfg,status,tax)
        missing.extend(unavailable)
        blockers.update(plan_blockers)
        if cfg.get('budget_deja_engage_eur') is None:
            missing.append('budget_deja_engage_eur')
        if cfg.get('risque_positions_ouvertes_eur') is None:
            missing.append('risque_positions_ouvertes_eur')
        if cfg.get('positions_ouvertes_nombre') is None:
            missing.append('positions_ouvertes_nombre')
        if not cfg.get('controle_spread_effectue'):
            blockers.add('SPREAD_NON_VERIFIE')
        if not cfg.get('titres_pea_verifies'):
            blockers.add('ELIGIBILITE_PEA_NON_VERIFIEE')
        # Research shortlist can include incomplete plans, but cannot bypass liquidity or audit.
        eligible_research = (liquidity is not None and liquidity >= cfg['liquidite_min_eur_jour']
                             and a.get('statut') == 'CONTROLES_INTERNES_OK'
                             and age is not None and 0 <= age <= cfg['cours_age_max_jours'])
        universe.append({'ticker':ticker,'date_seance':s.get('date_seance'),
            'score_exploratoire_100':base.get('score_exploratoire_100'),
            'configurations':base.get('configurations',[]),'groupes':s.get('groupes',[]),
            'indicateurs':{k:s.get(k) for k in ('close','mm20','mm50','mm200','rsi14','adx14',
                'macd_12_26','macd_signal9','macd_histogramme','atr14','atr_pct',
                'plus_bas_20j_precedent','plus_bas_55j_precedent','plus_haut_20j_precedent',
                'plus_haut_55j_precedent','volume','ratio_volume_20j','performance_20j_pct',
                'force_relative_cac40_20j_pct','valeur_echangee_moyenne20_eur_estimee')},
            'ttf':{'statut':status,'taux_pct':tax['taux_pct'] if status=='OUI' else (0 if status=='NON' else None),'source':tax['source']},
            'plan_exploratoire':plan,'raisons_rejet_et_reserves':sorted(blockers),
            'donnees_manquantes':sorted(set(missing)),'retenable_pour_etude':eligible_research,
            'autorise_signal_achat':False})
    ranked=sorted((x for x in universe if x['retenable_pour_etude'] and x['configurations']),
                  key=lambda x:(-(x['score_exploratoire_100'] or 0),x['ticker']))
    top=ranked[:cfg['max_dossiers']]
    return {'schema_version':'7.3','genere_utc':now.isoformat(),
            'sources':{'v4':v4.get('mise_a_jour_utc'),'v5':v5.get('genere_utc'),'v63':audit.get('genere_utc')},
            'regles':{'max_dossiers':cfg['max_dossiers'],'seuil_liquidite_eur':cfg['liquidite_min_eur_jour'],
                 'budget_tactique_eur':cfg['budget_tactique_total_eur'],
                 'risque_position_eur':cfg['risque_max_position_eur'],'risque_cumule_eur':cfg['risque_max_cumule_eur'],
                 'max_positions_ouvertes':cfg['positions_max'],'max_par_secteur':cfg['positions_par_secteur_max']},
            'compteurs':{'analyses':len(universe),'selectionnes':len(top),'exclus_recherche':sum(not x['retenable_pour_etude'] for x in universe)},
            'top_5_dossiers':top,'univers':universe,'achats_autorises':0,
            'avertissement':'Shortlist recherche uniquement. TTF par table ticker a confirmer par ISIN. Stop/resistance heuristiques, pas valides graphiquement. Prix Yahoo non independamment valides; spreads et positions reelles inconnus.'}


def main():
    v4=load(DATA/'indicateurs.json')
    v5=load(DATA/'screening.json')
    audit=load(DATA/'fiabilisation.json')
    config=load(CONFIG/'plans_v73.json')
    tax=load(CONFIG/'ttf_2026.json')
    result=generate(v4,v5,audit,config,tax)
    (DATA/'rapport_chatgpt_v73.json').write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    print('V7.3:',result['compteurs'],'achats autorises=0')


if __name__=='__main__':
    main()
