import unittest,sys
from pathlib import Path
from datetime import date
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fondamentaux_v86 import annual_metrics
from rapport_v86 import create,evaluate_one

def mock_statements(missing=False):
    dates=pd.to_datetime(['2025-12-31','2024-12-31','2023-12-31','2022-12-31'])
    def df(rows):return pd.DataFrame({d:{k:v[i] for k,v in rows.items()} for i,d in enumerate(dates)})
    inc=df({'Total Revenue':[200,180,160,140],'Gross Profit':[100,80,70,60],
      'EBIT':[40,30,25,20],'Net Income':[30,20,15,10], 'Pretax Income':[40,30,25,20], 'Tax Provision':[10,8,6,5]})
    bal=df({'Total Assets':[400,380,360,340],'Stockholders Equity':[150,140,130,120],
      'Total Debt':[60,70,80,90],'Cash And Cash Equivalents':[40,30,25,20],
      'Current Assets':[90,80,75,70],'Current Liabilities':[45,50,55,60],
      'Ordinary Shares Number':[10,10,10,10]})
    cash=df({'Operating Cash Flow':[45,32,26,20],'Free Cash Flow':[35,25,20,15]})
    if missing:bal=bal.drop('Ordinary Shares Number')
    return inc,bal,cash
class TestV86(unittest.TestCase):
 def test_piotroski_and_roic(self):
    out=annual_metrics(*mock_statements())
    self.assertEqual(out['piotroski_f_score'],9)
    self.assertGreater(out['roic_pct'],0)
    self.assertGreater(out['croissance_ca_cagr_3ans_pct'],0)
 def test_missing_score_not_imputed(self):
    out=annual_metrics(*mock_statements(True))
    self.assertIsNone(out['piotroski_f_score'])
    self.assertEqual(out['piotroski_couverture'],8)
 def test_coverage_penalty(self):
    cfg={'version':'8.6','max_global':5,'max_par_strategie':5,'liquidite_min_eur_jour':1000000,
      'couverture_min_pct':60,'anciennete_comptes_max_mois':21,
      'poids':{'technique':35,'fondamental':45,'adequation_strategie':20},
      'fundamental':{'poids':{'qualite_actuelle':30,'qualite_pluriannuelle':30,'valorisation_sectorielle':20,'solidite':20},'min_paires_comparables_secteur':5}}
    base={'ticker':'X.PA','score_global_100':85,'score_technique_100':90,'score_fondamental_100':100,'couverture_fondamentale_pct':50,
      'indicateurs_fondamentaux':{},'indicateurs_techniques':{'valeur_echangee_moyenne20_eur_estimee':2000000},
      'strategies':{'cassure':{'adequation_pct':100,'criteres_tous_satisfaits':True}},'exclusions_recherche':[]}
    x=evaluate_one(base,None,'Technology',{},cfg,date(2026,10,30))
    self.assertLess(x['score_fondamental_prudent_100'],100)
    self.assertFalse(x['admissible_recherche'])
 def test_no_trades_and_strategic_separation(self):
    cfg={'version':'8.6','max_global':5,'max_par_strategie':5,'liquidite_min_eur_jour':1000000,
      'couverture_min_pct':60,'anciennete_comptes_max_mois':21,
      'poids':{'technique':35,'fondamental':45,'adequation_strategie':20},
      'fundamental':{'poids':{'qualite_actuelle':30,'qualite_pluriannuelle':30,'valorisation_sectorielle':20,'solidite':20},'min_paires_comparables_secteur':5}}
    old={'schema_version':'8.3','univers':[]}
    out=create(old,{'schema_version':'8.6-finances','fiches':{}},{'fiches':{}},cfg)
    self.assertEqual(out['achats_autorises'],0)
    self.assertEqual(len(out['top_5_par_strategie']),3)
 def test_no_invalid_security(self):
    cfg={'version':'8.6','max_global':6,'max_par_strategie':5,'liquidite_min_eur_jour':1000000,'poids':{'technique':35,'fondamental':45,'adequation_strategie':20},'fundamental':{'poids':{'qualite_actuelle':30,'qualite_pluriannuelle':30,'valorisation_sectorielle':20,'solidite':20}}}
    with self.assertRaises(ValueError):create({'schema_version':'8.3','univers':[]},{'schema_version':'8.6-finances'},{'fiches':{}},cfg)
if __name__=='__main__':unittest.main()
