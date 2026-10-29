import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fondamentaux_v8 import extract,evaluate
from rapport_v8 import create
class TestV8(unittest.TestCase):
 def test_missing(self):
  r={'donnees':extract({'longName':'Test','sector':'Industrials'})}
  e=evaluate(r)
  self.assertEqual(e['couverture_score_pct'],0)
  self.assertIsNone(e['score_observe_sur_indicateurs_disponibles_100'])
 def test_financial_sector(self):
  r={'donnees':extract({'longName':'Test','sector':'Financial Services','trailingPE':12,'returnOnEquity':0.2})}
  self.assertFalse(evaluate(r)['comparable_avec_secteur_financier'])
 def test_merged(self):
  o=create({'schema_version':'7.3','regles':{'max_dossiers':5},'top_5_dossiers':[{'ticker':'AA.PA'}]}, {'schema_version':'8.0','fiches':{},'erreurs':{}})
  self.assertEqual(o['nombre_dossiers'],1)
  self.assertEqual(o['achats_autorises'],0)
  self.assertEqual(o['dossiers'][0]['donnees_fondamentales_manquantes'],['FICHE_ENTIERE'])
if __name__=='__main__': unittest.main()
