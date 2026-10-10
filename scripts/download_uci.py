"""Download the public UCI "Default of credit card clients" dataset (CC BY 4.0).

Yeh, I. C., & Lien, C. H. (2009). Expert Systems with Applications, 36(2), 2473-2480.
https://archive.ics.uci.edu/dataset/350/default+of+credit+card+clients
Run from the repository root: python scripts/download_uci.py
"""
import io
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

URL = "https://archive.ics.uci.edu/static/public/350/default+of+credit+card+clients.zip"
OUT = Path(__file__).resolve().parents[1] / "data" / "raw" / "uci_credit.csv"


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    print("Downloading", URL)
    with urllib.request.urlopen(URL, timeout=120) as resp:
        blob = resp.read()
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        name = next(n for n in z.namelist() if n.endswith(".xls"))
        with z.open(name) as f:
            df = pd.read_excel(io.BytesIO(f.read()), header=1)
    df = df.rename(columns={"default payment next month": "default"})
    df.to_csv(OUT, index=False)
    print(f"Saved {len(df):,} rows to {OUT}")


if __name__ == "__main__":
    main()
