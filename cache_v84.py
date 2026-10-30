"""V8.4: persistent incremental Yahoo OHLCV cache, single 5-year source.
No independent market-data validation, and no buy decisions.
"""
from __future__ import annotations
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / 'config' / 'cache_v84.json'
CACHE = ROOT / 'data' / 'historique_long'
COLS = ['Open', 'High', 'Low', 'Close', 'Volume', 'Adj Close']
LOG = logging.getLogger('cache_v84')


def normalize(df):
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = df.columns.get_level_values(0)
    if df.empty:
        raise ValueError('HISTORIQUE_VIDE')
    if any(col not in df.columns for col in COLS):
        raise ValueError('COLONNES_MANQUANTES')
    df = df[COLS].copy()
    index = pd.to_datetime(df.index)
    # Preserve exchange-local session dates; UTC conversion shifts Paris midnight.
    if index.tz is not None:
        index = index.tz_localize(None)
    df.index = index.normalize()
    if df.index.has_duplicates:
        raise ValueError('DATES_DUPLIQUEES_SOURCE')
    df = df.sort_index()
    if df[COLS].isna().any().any():
        raise ValueError('VALEUR_MANQUANTE')
    if (df[['Open','High','Low','Close','Adj Close']] <= 0).any().any():
        raise ValueError('COURS_NON_POSITIF')
    if (df['Volume'] < 0).any():
        raise ValueError('VOLUME_NEGATIF')
    return df


class Cache:
    def __init__(self, original_download, config=None, directory=None, now=None):
        self.original_download = original_download
        self.cfg = config if config is not None else json.loads(CONFIG.read_text(encoding='utf-8'))
        self.directory = Path(directory) if directory else CACHE
        self.now = now or datetime.now(ZoneInfo('Europe/Paris'))
        self.stats = {'full': 0, 'incremental': 0, 'fallback': 0, 'unchanged': 0, 'errors': {}}
        self._memory = {}

    def path(self, ticker):
        if not ticker or any(x in ticker for x in ('/', '\\', '..')):
            raise ValueError('TICKER_INVALIDE')
        return self.directory / f'{ticker}.csv'

    def read(self, ticker):
        path = self.path(ticker)
        if not path.is_file():
            return None
        try:
            frame = pd.read_csv(path, index_col='Date', parse_dates=['Date'])
            return normalize(frame)
        except (ValueError, KeyError, pd.errors.ParserError) as exc:
            LOG.warning('Cache invalide pour %s: %s; reconstruction complete', ticker, exc)
            return None

    def remote(self, ticker, start=None):
        # End exclusive, requesting tomorrow also allows the current session, if present.
        end = (self.now.date() + timedelta(days=1)).isoformat()
        opts = {'interval': '1d', 'auto_adjust': False, 'progress': False, 'threads': False}
        if start is None:
            opts['start'] = (pd.Timestamp(self.now.date()) - pd.DateOffset(years=self.cfg['historique_annees'], days=7)).date().isoformat()
        else:
            opts['start'] = pd.Timestamp(start).date().isoformat()
        opts['end'] = end
        return normalize(self.original_download(ticker, **opts))

    def monthly_full(self):
        # First Saturday of each month (workflow Saturday 08:00 Europe/Paris).
        d = self.now.date()
        return d.weekday() == 5 and d.day <= 7 and self.cfg['verification_complete_mensuelle']

    def _save(self, ticker, df, old):
        self.directory.mkdir(parents=True, exist_ok=True)
        if old is not None and df.equals(old):
            self.stats['unchanged'] += 1
            return
        tmp = self.path(ticker).with_suffix('.csv.tmp')
        df.to_csv(tmp, index_label='Date', date_format='%Y-%m-%d', float_format='%.10g')
        tmp.replace(self.path(ticker))

    def get(self, ticker):
        if ticker in self._memory:
            return self._memory[ticker].copy()
        old = self.read(ticker)
        try:
            if old is None or self.monthly_full():
                df = self.remote(ticker)
                self.stats['full'] += 1
            else:
                since = old.index[-1] - pd.Timedelta(days=self.cfg['chevauchement_jours'])
                new = self.remote(ticker, since)
                shared = old.index.intersection(new.index)
                # Changes of the adjustment factor may affect the entire history.
                changed_factor = False
                if len(shared):
                    a = (old.loc[shared, 'Adj Close'] / old.loc[shared, 'Close']).astype(float)
                    b = (new.loc[shared, 'Adj Close'] / new.loc[shared, 'Close']).astype(float)
                    changed_factor = bool(((a - b).abs() > self.cfg['tolerance_facteur_ajustement']).any())
                if changed_factor:
                    LOG.info('Adjusted-price factor changed for %s; fetching full 5y', ticker)
                    df = self.remote(ticker)
                    self.stats['fallback'] += 1
                else:
                    df = pd.concat([old.loc[~old.index.isin(new.index)], new]).sort_index()
                    self.stats['incremental'] += 1
            floor = pd.Timestamp(self.now.date()) - pd.DateOffset(years=self.cfg['historique_annees'])
            df = normalize(df.loc[df.index >= floor])
            if len(df) < self.cfg['minimum_seances_pour_calcul']:
                raise ValueError('HISTORIQUE_TROP_COURT')
            self._save(ticker, df, old)
        except Exception as exc:
            self.stats['errors'][ticker] = str(exc)[:200]
            # Fail closed: no stale source silently represented as refreshed.
            raise
        self._memory[ticker] = df
        return df.copy()

    def download(self, ticker, *args, **kwargs):
        # Compatible adapter for existing yf.download(ticker, period='2y'|'5y', ...).
        if not isinstance(ticker, str):
            raise TypeError('Téléchargement groupé non pris en charge par cet adaptateur')
        return self.get(ticker)

    def save_stats(self):
        out = ROOT / 'data' / 'cache_v84_stats.json'
        out.write_text(json.dumps({'version':'8.4','updated_at':self.now.isoformat(),**self.stats},indent=2,ensure_ascii=False),encoding='utf-8')
