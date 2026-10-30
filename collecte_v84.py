"""Compatibility runner: cache OHLCV, preserve V4 and V6.3 outputs."""
import argparse
import logging
import yfinance as yf
from cache_v84 import Cache


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('step', choices=['pipeline', 'collecte', 'audit'])
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    original = yf.download
    cache = Cache(original)
    yf.download = cache.download
    try:
        if args.step in ('pipeline', 'collecte'):
            import collecte
            collecte.main()
        if args.step == 'pipeline':
            import screening
            screening.main()
        if args.step in ('pipeline', 'audit'):
            import fiabilisation
            fiabilisation.main()
    finally:
        yf.download = original
        cache.save_stats()
    print('CACHE V8.4:', cache.stats)


if __name__ == '__main__':
    main()
