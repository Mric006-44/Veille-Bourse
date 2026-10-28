"""Veille-Bourse V6.2 - recherche exploratoire + selection apprentissage uniquement.
Aucun achat autorise. Ne modifie pas V6.1. Ne telecharge pas de donnees.
"""
from __future__ import annotations
import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from portfolio_backtest import load_history, evaluate

ROOT = Path(__file__).resolve().parent
CFG = ROOT / 'config' / 'robustesse.json'
BASE = ROOT / 'config' / 'portfolio.json'
WATCH = ROOT / 'config' / 'watchlist.json'
HIST = ROOT / 'data' / 'historique'
OUTPUT = ROOT / 'data' / 'robustesse.json'


def metrics(trades):
    pnl = np.asarray([float(x['pnl_eur']) for x in trades], dtype=float)
    gains = float(pnl[pnl > 0].sum()) if len(pnl) else 0.0
    losses = float(-pnl[pnl < 0].sum()) if len(pnl) else 0.0
    return {
        'nombre_trades': int(len(pnl)),
        'pnl_net_eur': round(float(pnl.sum()), 2),
        'pnl_moyen_eur': round(float(pnl.mean()), 2) if len(pnl) else None,
        'taux_reussite_pct': round(100 * float((pnl > 0).mean()), 2) if len(pnl) else None,
        'profit_factor': round(gains / losses, 3) if losses else None,
        'perte_max_trade_eur': round(float(pnl.min()), 2) if len(pnl) else None,
    }


def split_metrics(sim, cutoff):
    trades = sim['trades']
    before = [t for t in trades if t['entry_date'] < cutoff]
    after = [t for t in trades if t['entry_date'] >= cutoff]
    return {'apprentissage': metrics(before), 'test': metrics(after)}


def load_data(base):
    watch = json.loads(WATCH.read_text(encoding='utf-8'))
    symbols = sorted({t for group in ('cac40_indicatif','actions_supplementaires','etf') for t in watch.get(group, [])})
    data, excluded = {}, {}
    for ticker in symbols:
        try:
            data[ticker] = load_history(HIST / (ticker + '.csv'), base)
        except Exception as e:
            excluded[ticker] = str(e)[:200]
    if len(data) < 3:
        raise RuntimeError('Trop peu de titres fiables; pas de publication')
    return data, excluded, symbols


def main():
    options = json.loads(CFG.read_text(encoding='utf-8'))
    base = json.loads(BASE.read_text(encoding='utf-8'))
    data, excluded, symbols = load_data(base)
    # Date de separation fixe, choisie AVANT de visualiser les essais V6.2.
    cutoff = str(options['date_separation'])
    all_dates = sorted(set.intersection(*(set(d.index) for d in data.values())))
    first, last = all_dates[205].date().isoformat(), all_dates[-1].date().isoformat()
    if not (first < cutoff < last):
        raise ValueError(f'Date separation {cutoff} hors de la periode exploitable {first} - {last}')
    scenarios = []
    for atr in options['multiplicateurs_atr']:
        for duration in options['durees_seances']:
            c = copy.deepcopy(base)
            c['stop_atr_multiple'] = float(atr)
            c['max_holding_sessions'] = int(duration)
            sim = evaluate(data, c)
            m = split_metrics(sim, cutoff)
            scenarios.append({'atr': float(atr), 'duree_seances': int(duration),
                              'apprentissage': m['apprentissage'], 'test': m['test'],
                              'risque_max_observe_eur': sim['metrics']['total']['max_simultaneous_stop_risk_eur']})

    # On ne consulte JAMAIS le resultat test pour choisir les parametres.
    minimum = int(options['minimum_trades_apprentissage'])
    def admissible(s):
        m = s['apprentissage']
        return m['nombre_trades'] >= minimum and m['profit_factor'] is not None and m['profit_factor'] > 1
    eligible = [s for s in scenarios if admissible(s)]
    # Choix objectif predefini: PnL sur apprentissage, puis robustesse (PF), puis complexite.
    eligible.sort(key=lambda s: (-s['apprentissage']['pnl_net_eur'], -s['apprentissage']['profit_factor'], s['atr'], s['duree_seances']))
    best = eligible[0] if eligible else None

    stress = []
    if best is not None:
        for slip in options['slippages_stress_pct']:
            c = copy.deepcopy(base)
            c['stop_atr_multiple'] = best['atr']
            c['max_holding_sessions'] = best['duree_seances']
            c['slippage_pct_per_side'] = float(slip)
            sim = evaluate(data, c)
            m = split_metrics(sim, cutoff)
            stress.append({'slippage_pct_par_cote': float(slip), 'apprentissage': m['apprentissage'], 'test': m['test']})
    result = {
        'schema_version': '6.2', 'generated_utc': datetime.now(timezone.utc).isoformat(),
        'periode': {'premiere_date_signaux': first, 'date_separation': cutoff, 'derniere_date': last},
        'univers': {'configure': len(symbols), 'retenu': len(data), 'exclus': excluded},
        'configuration': options, 'frais_pct_par_cote': base['fee_pct_per_side'],
        'methode_selection': 'Seuls les resultats apprentissage determinent le choix; test jamais utilise pour selection.',
        'scenarios': scenarios,
        'selection_apprentissage': None if best is None else {'atr': best['atr'], 'duree_seances': best['duree_seances'], 'apprentissage': best['apprentissage']},
        'resultat_test_scenario_selectionne': None if best is None else best['test'],
        'stress_slippage': stress,
        'statut': 'AUCUNE_CONFIGURATION_PASSANT_LE_FILTRE' if best is None else 'CONFIGURATION_EXPLORATOIRE_NON_VALIDEE',
        'achats_autorises': 0,
        'limites': [
            'Selection sur historique et test unique; risque de surajustement et de reemploi des donnees',
            'Le split est base sur les dates entree; un trade entre en apprentissage peut se terminer apres le split',
            'Signaux calcules en mode V6.1 avec choix de strategie fixe; pas une optimisation de seuils RSI/ADX',
            'Biais de survivance: liste actuelle appliquee au passe',
            'Historique ajuste Yahoo non certifie; splits/dividendes approximatifs',
            'Spread et slippage reels inconnus; risque stop non garanti en cas de gap',
            'Ce test n etablit aucune probabilite future de gain et n autorise aucun achat'
        ]
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print('V6.2:', len(scenarios), 'scenarios,', len(data), 'titres, statut', result['statut'])

if __name__ == '__main__':
    main()
