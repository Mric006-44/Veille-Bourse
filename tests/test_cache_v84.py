import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cache_v84 import Cache


def frame():
    index = pd.bdate_range('2022-01-03', '2026-10-30')
    close = pd.Series(np.arange(len(index), dtype=float) / 100 + 20, index=index)
    return pd.DataFrame({'Open':close,'High':close+1,'Low':close-1,'Close':close,'Volume':100000,'Adj Close':close}, index=index)


class Source:
    def __init__(self):
        self.frame = frame()
        self.calls = []
    def __call__(self, ticker, **kw):
        self.calls.append(kw)
        x = self.frame
        return x[(x.index >= pd.Timestamp(kw['start'])) & (x.index < pd.Timestamp(kw['end']))].copy()


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.src = Source()
        self.cfg = {'historique_annees':5,'chevauchement_jours':10,'verification_complete_mensuelle':True,'tolerance_facteur_ajustement':1e-5,'minimum_seances_pour_calcul':210}
        self.now = datetime(2026,10,30,19,0,tzinfo=ZoneInfo('Europe/Paris'))
    def tearDown(self):
        self.tmp.cleanup()
    def cache(self):
        return Cache(self.src, self.cfg, self.tmp.name, now=self.now)
    def test_incremental_after_initial(self):
        first=self.cache(); self.assertGreater(len(first.get('AIR.PA')),1000)
        second=self.cache(); second.get('AIR.PA')
        self.assertEqual(second.stats['incremental'],1)
        self.assertGreater(pd.Timestamp(self.src.calls[-1]['start']), pd.Timestamp('2026-10-01'))
    def test_update_overlapping_last_session(self):
        self.cache().get('AIR.PA')
        self.src.frame.loc['2026-10-29','Close']=99.0
        second=self.cache()
        self.assertEqual(second.get('AIR.PA').loc['2026-10-29','Close'],99)
    def test_adjustment_change_forces_full(self):
        self.cache().get('AIR.PA')
        self.src.frame['Adj Close'] *= 0.95
        second=self.cache(); second.get('AIR.PA')
        self.assertEqual(second.stats['fallback'],1)
    def test_missing_source_is_error_not_stale_success(self):
        self.cache().get('AIR.PA')
        def fail(*args, **kwargs): raise ConnectionError('Yahoo unavailable')
        c=Cache(fail,self.cfg,self.tmp.name,now=self.now)
        with self.assertRaises(ConnectionError): c.get('AIR.PA')
        self.assertIn('AIR.PA',c.stats['errors'])
    def test_exchange_timezone_keeps_session_date(self):
        from cache_v84 import normalize
        f=frame().iloc[:3].copy()
        f.index=f.index.tz_localize('Europe/Paris')
        self.assertEqual(str(normalize(f).index[0].date()), '2022-01-03')

    def test_memory_one_fetch_per_workflow_step(self):
        cache=self.cache(); cache.get('AIR.PA');cache.get('AIR.PA')
        self.assertEqual(len(self.src.calls),1)


if __name__ == '__main__': unittest.main()
