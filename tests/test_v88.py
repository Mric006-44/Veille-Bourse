import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from plans_v88 import plan
from backtest_v87 import tax_status,summarize
CFG={'liquidite_min_eur':1000000,'stop_atr_min_multiple':1.5,'marge_sous_support_atr':.2,
     'ratio_gain_risque_brut_min':2,'frais_pct_par_ordre':.35,'slippage_pct_par_cote':.1,
     'ttf_pct':.4,'risque_par_position_eur':20,'capital_eur':2000,
     'risque_cumule_eur':60,'positions_reelles':[],'positions_reelles_exhaustives_confirmees':False,
     'verification_pea':False,'verification_spread':False,'validation_source_independante':False,
     'validation_catalyseur':False,'validation_graphique':False}
T={'close':100,'atr14':2,'mm20':97,'mm50':94,'plus_bas_20j_precedent':90,
   'plus_bas_55j_precedent':85,'plus_haut_20j_precedent':110,'plus_haut_55j_precedent':120,
   'valeur_echangee_moyenne20_eur_estimee':2000000}
S={'admissible_recherche':True,'score_global_v86_100':85,'strategies':{}}
OLD={'date_seance':'2026-10-30'}
TAX={'oui':['TEST.PA'],'non':[]}
from datetime import date
class Test(unittest.TestCase):
 def test_tax(self):
  self.assertEqual(tax_status('OTHER.PA',TAX),'INCONNUE')
 def test_risk(self):
  p=plan('TEST.PA',T,OLD,S,{},CFG,TAX,date(2026,10,30))
  self.assertFalse(p['achat_autorise'])
  self.assertLessEqual(p['plan_exploratoire']['risque_estime_eur'],20)
  self.assertGreaterEqual(p['plan_exploratoire']['ratio_gain_risque_brut'],2)
  self.assertIn('REGISTRE_POSITIONS_NON_CONFIRME',p['blocages'])
 def test_missing_ttf(self):
  p=plan('OTHER.PA',T,OLD,S,{},CFG,TAX,date(2026,10,30))
  self.assertIsNone(p['plan_exploratoire']['quantite_theorique'])
 def test_insufficient_rr(self):
  t={**T,'plus_haut_20j_precedent':101}
  p=plan('TEST.PA',t,OLD,S,{},CFG,TAX,date(2026,10,30))
  self.assertIn('RATIO_BRUT_INSUFFISANT',p['blocages'])
 def test_summary(self):
  self.assertEqual(summarize([],30)['statut'],'ECHANTILLON_INSUFFISANT')
if __name__=='__main__':unittest.main()
