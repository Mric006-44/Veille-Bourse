"""Collecte indicative d'actions cotées à Paris ; liste à réviser lors des changements du CAC 40."""
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

# Liste indicative des grandes valeurs parisiennes. Vérifier les composants exacts du CAC40.
TICKERS = [
    "AC.PA", "AI.PA", "AIR.PA", "ALO.PA", "MT.AS", "CS.PA", "BNP.PA", "EN.PA",
    "CAP.PA", "CA.PA", "ACA.PA", "BN.PA", "DSY.PA", "EDEN.PA", "ENGI.PA", "EL.PA",
    "ERF.PA", "RMS.PA", "KER.PA", "LR.PA", "OR.PA", "MC.PA", "ML.PA", "ORA.PA",
    "RI.PA", "PUB.PA", "RNO.PA", "SAF.PA", "SGO.PA", "SAN.PA", "SU.PA", "GLE.PA",
    "STLAP.PA", "STMPA.PA", "TEP.PA", "HO.PA", "TTE.PA", "URW.PA", "VIE.PA", "DG.PA",
]


def opt_float(value, digits=4):
    try:
        x = float(value)
        return round(x, digits) if np.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def calculate(df):
    df = df.dropna(subset=["Close", "High", "Low", "Volume"]).copy()
    if len(df) < 210:
        raise ValueError(f"Historique insuffisant: {len(df)} séances (<210)")
    close, high, low = df["Close"], df["High"], df["Low"]
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    true_range = pd.concat([high-low, (high-close.shift()).abs(), (low-close.shift()).abs()], axis=1).max(axis=1)
    atr = true_range.ewm(alpha=1/14, adjust=False).mean()
    vol20 = df["Volume"].rolling(20).mean()
    return {
        "date_seance": str(df.index[-1].date()),
        "close": opt_float(close.iloc[-1]),
        "volume": int(df["Volume"].iloc[-1]),
        "volume_moyen_20j": opt_float(vol20.iloc[-1], 0),
        "ratio_volume_20j": opt_float(df["Volume"].iloc[-1] / vol20.iloc[-1]) if vol20.iloc[-1] else None,
        "rsi14": opt_float(rsi.iloc[-1], 2),
        "macd_12_26": opt_float(macd.iloc[-1]),
        "macd_signal9": opt_float(signal.iloc[-1]),
        "macd_histogramme": opt_float((macd-signal).iloc[-1]),
        "mm20": opt_float(close.rolling(20).mean().iloc[-1]),
        "mm50": opt_float(close.rolling(50).mean().iloc[-1]),
        "mm200": opt_float(close.rolling(200).mean().iloc[-1]),
        "atr14": opt_float(atr.iloc[-1]),
        "seances": len(df),
    }


def main():
    results, errors = {}, {}
    for ticker in TICKERS:
        try:
            df = yf.download(ticker, period="2y", interval="1d", auto_adjust=False, progress=False, threads=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            if df.empty:
                raise ValueError("Aucune donnée")
            results[ticker] = calculate(df)
            print("OK", ticker)
        except Exception as exc:
            errors[ticker] = str(exc)
            print("ERREUR", ticker, exc)
    if not results:
        raise RuntimeError("Aucune donnée exploitable : les fichiers existants ne seront pas écrasés")
    payload = {
        "mise_a_jour_utc": datetime.now(timezone.utc).isoformat(),
        "source": "Yahoo Finance via yfinance (source non officielle, données potentiellement différées)",
        "univers": "Liste indicative de grandes capitalisations ; non certifiée comme composition actuelle du CAC 40",
        "indicateurs": results,
        "erreurs": errors,
        "avertissement": "Données indicatives, vérifier prix, fraîcheur et conditions avant décision d'investissement."
    }
    path = Path("data/indicateurs.json")
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Écrit : {path}; {len(results)} titres, {len(errors)} erreurs")


if __name__ == "__main__":
    main()
