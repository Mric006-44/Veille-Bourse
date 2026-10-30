import sys, json, tempfile, unittest
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from rapport_v83 import validate_config, enrich_fundamental, enriched_technical, make_report, strategy_checks

CFG=json.loads((Path(__file__).resolve().parents[1]/'config/analyse_v83.json').read_text())
class TestV83(unittest.TestCase):
    def test_config(self):
        validate_config(CFG)
        changed=json.loads(json.dumps(CFG))
        changed['securite_non_modifiable_par_scoring']['risque_max_position_eur']=30
        with self.assertRaises(ValueError):validate_config(changed)

    def test_missing_fundamentals_not_fabricated(self):
        f=enrich_fundamental({'donnees':{'identite':{'sector':'Industrials','marketCap':100},'solidite':{'totalDebt':15,'totalCash':5,'freeCashflow':8}}})
        self.assertEqual(f['dette_nette'],10)
        self.assertEqual(f['fcf_yield_pct'],8)
        self.assertIsNone(f['roic_pct'])
        self.assertIsNone(f['piotroski_f_score'])
        self.assertIsNone(f['marge_fcf_pct'])

    def test_technical_252(self):
        with tempfile.TemporaryDirectory() as tmp:
            df=pd.DataFrame({'Date':pd.bdate_range('2025-01-01',periods=260),
                'Close':[100+i*.1 for i in range(260)],'High':[101+i*.1 for i in range(260)],
                'Low':[99+i*.1 for i in range(260)]})
            df.to_csv(Path(tmp)/'ZZ.PA.csv',index=False)
            t=enriched_technical('ZZ.PA',{},Path(tmp))
            self.assertIsNotNone(t['performance_252j_pct'])
            self.assertIsNotNone(t['volatilite_20j_pct'])
            self.assertIsNotNone(t['plus_haut_252j_precedent'])

    def test_shortlists_and_liquidity(self):
        v4={'schema_version':'4.0','mise_a_jour_utc':'X','indicateurs':{}}
        v73={'schema_version':'7.3','sources':{'v4':'X'},'univers':[]}
        v8={'schema_version':'8.0','fiches':{}}
        for i in range(8):
            ticker=f'ZZ{i}.PA'
            v4['indicateurs'][ticker]={'close':100,'mm200':95,'mm50':98,'atr14':3,
                'rsi14':55,'adx14':25,'macd_histogramme':1,'plus_haut_20j_precedent':99,
                'ratio_volume_20j':1.5,'valeur_echangee_moyenne20_eur_estimee': 0.5e6 if i==0 else 2e6,
                'date_seance':'2026-10-30','anomalies':[]}
            v73['univers'].append({'ticker':ticker,'retenable_pour_etude':True,
                'score_exploratoire_100':80,'plan_exploratoire':None,'raisons_rejet_et_reserves':['PAS_DE_SECONDE_SOURCE']})
            v8['fiches'][ticker]={'donnees':{'identite':{'sector':'Industrials','marketCap':1e9},
                 'solidite':{'freeCashflow':8e7,'totalDebt':8e7,'totalCash':2e7},
                 'valorisation':{'forwardPE':12},'croissance':{'revenueGrowth':0.15},
                 'rentabilite':{'operatingMargins':0.2,'returnOnEquity':0.15}}}
        with tempfile.TemporaryDirectory() as tmp:
            report=make_report(v4,v73,v8,CFG,Path(tmp))
        self.assertEqual(report['achats_autorises'],0)
        self.assertEqual(len(report['top_5_global']),5)
        self.assertTrue(all(len(x)<=5 for x in report['top_5_par_strategie'].values()))
        self.assertFalse(any(x['ticker']=='ZZ0.PA' for x in report['top_5_global']))
        self.assertTrue(all(x['achat_autorise'] is False for x in report['top_5_global']))

    def test_missing_annual_not_a_pass(self):
        t={'rsi14':55,'adx14':25,'close':110,'mm200':90,'macd_histogramme':1}
        f={'croissance_ca_pct':8}
        checks,_=strategy_checks('croissance_momentum',t,f,CFG['classement']['strategies']['croissance_momentum'])
        self.assertFalse(next(x['satisfait'] for x in checks if x['critere']=='PERFORMANCE_1_AN'))

if __name__=='__main__':unittest.main()
