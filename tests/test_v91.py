import unittest
from datetime import date
from catalyseurs_v90 import validate
from rapport_v91 import evaluate,create

class TestV91(unittest.TestCase):
    def test_catalyseur_source_obligatoire(self):
        res,err=validate([{'ticker':'IPN.PA','evenement':'Publication','source':'Societe',
            'url_source':'https://example.org/doc','date_publication':'2026-10-20','date_reexamen':'2026-11-20'}],date(2026,10,30))
        self.assertEqual(len(err),0);self.assertEqual(len(res['IPN.PA']),1)
    def test_rejet_catalyseur_sans_url(self):
        res,err=validate([{'ticker':'IPN.PA','evenement':'Rumeur','source':'Inconnu',
            'url_source':'','date_publication':'2026-10-20','date_reexamen':'2026-11-20'}],date(2026,10,30))
        self.assertFalse(res);self.assertEqual(len(err),1)
    def test_objectif_unique_et_zero_achat(self):
        item={'ticker':'IPN.PA','secteur':'Healthcare','score_global_v86_100':70,
          'plan_exploratoire_v73':{'resistance_cible':120,'stop_invalidation_candidat':90}}
        result=evaluate(item,{}, {}, {'Healthcare':10})
        self.assertEqual(result['objectif_unique_indicatif'],120)
        self.assertFalse(result['achat_autorise'])
    def test_rapport_pas_de_scenarios(self):
        r=create({'schema_version':'8.6','top_5_global':[{'ticker':'A'}],
          'univers':[{'ticker':'A','secteur':'Technology'}]},
          {'schema_version':'8.3','univers':[{'ticker':'A'}]}, {'genere_utc':'now','catalyseurs':{}})
        self.assertEqual(r['achats_autorises'],0)
        self.assertEqual(len(r['top_5_global']),1)
    def test_risque_portefeuille(self):
        # Import simple, sans exécuter de téléchargements.
        import sys, types
        from unittest.mock import patch
        # Les modules V8.7 existent dans le dépôt cible ; stub uniquement pour ce test isolé.
        stub=types.ModuleType('backtest'); stub.indicators=lambda d:None; stub.signal=lambda *a:False
        legacy=types.ModuleType('backtest_v87'); legacy.load_history=lambda p:None; legacy.tax_status=lambda t,x:'INCONNUE'
        with patch.dict(sys.modules, {'backtest':stub, 'backtest_v87':legacy}):
            from backtest_v89 import simulate_portfolio
        c={'capital_eur':2000,'positions_max':3,'positions_par_secteur_max':2,
          'frais_pct_par_ordre':0.35,'ttf_pct':0.4,'slippage_pct_par_cote':0.1,
          'stop_atr_min_multiple':1.5,'marge_sous_support_atr':0.2,
          'risque_par_position_eur':20,'risque_cumule_eur':60,'liquidite_min_eur':1000000,
          'simulation':{'strategies':['TENDANCE'],'max_conservation_seances':60}}
        x=simulate_portfolio({}, {}, {}, c)
        self.assertEqual(x['max_positions_observe'],0)
        self.assertEqual(x['capital_initial_eur'],2000)

if __name__=='__main__':unittest.main()
