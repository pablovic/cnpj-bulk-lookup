"""
Run this from your cnpj_bulk folder to verify the municipality lookup works:
    python test_lookup.py
"""
import os, sys

print("=" * 55)
print("CNPJ Bulk — Municipality Lookup Diagnostic")
print("=" * 55)

# ── 1. Check xlrd is installed ────────────────────────────────
try:
    import xlrd
    print(f"✅ xlrd {xlrd.__version__} installed")
except ImportError:
    print("❌ xlrd NOT installed — run:  pip install xlrd>=2.0.1")
    sys.exit(1)

# ── 2. Check the XLS file exists ─────────────────────────────
here     = os.path.dirname(os.path.abspath(__file__))
xls_path = os.path.join(here, "dim_municipality",
                        "RELATORIO_DTB_BRASIL_2024_MUNICIPIOS.xls")
if os.path.exists(xls_path):
    print(f"✅ XLS file found:\n   {xls_path}")
else:
    print(f"❌ XLS file NOT found at:\n   {xls_path}")
    print("\n   Make sure the folder structure is:")
    print("   cnpj_bulk/")
    print("   └── dim_municipality/")
    print("       └── RELATORIO_DTB_BRASIL_2024_MUNICIPIOS.xls")
    sys.exit(1)

# ── 3. Try loading it ─────────────────────────────────────────
import pandas as pd
try:
    df = pd.read_excel(xls_path, dtype=str, header=6, engine="xlrd")
    df = df.dropna(how="all").dropna(axis=1, how="all")
    df = df.rename(columns=lambda c: c.strip())
    print(f"✅ XLS loaded — {len(df)} rows, columns: {df.columns.tolist()}")
except Exception as e:
    print(f"❌ Failed to read XLS: {e}")
    sys.exit(1)

# ── 4. Check required columns exist ──────────────────────────
required = ["Nome_UF", "Nome_Município", "Código Município Completo"]
missing  = [c for c in required if c not in df.columns]
if missing:
    print(f"❌ Missing columns: {missing}")
    print(f"   Columns found: {df.columns.tolist()}")
    sys.exit(1)
else:
    print(f"✅ All required columns present")

# ── 5. Run lookup tests ───────────────────────────────────────
from cnpj_client import lookup_codigo_municipio, _MUNICIPIO_LOOKUP
print(f"✅ Lookup dictionary loaded: {len(_MUNICIPIO_LOOKUP)} entries")
print()
print("Lookup tests:")

tests = [
    ("São Paulo",         "São Paulo",           "3550308"),
    ("Rio de Janeiro",    "Rio de Janeiro",       "3304557"),
    ("Rio Grande do Sul", "Santa Bárbara do Sul", "4316709"),
    ("Minas Gerais",      "Belo Horizonte",       "3106200"),
    ("Bahia",             "Salvador",             "2927408"),
    # Duplicate city name — must resolve by UF
    ("Paraíba",           "Alagoinha",            "2500502"),
    ("Pernambuco",        "Alagoinha",            "2600609"),
]

all_pass = True
for estado, cidade, expected in tests:
    result = lookup_codigo_municipio(estado, cidade)
    ok     = result == expected
    icon   = "✅" if ok else "❌"
    if not ok:
        all_pass = False
    print(f"  {icon}  {estado:<25} + {cidade:<25} → {result or '(empty)'}"
          + ("" if ok else f"  ← expected {expected}"))

print()
if all_pass:
    print("✅ All tests passed! The lookup is working correctly.")
else:
    print("⚠️  Some tests failed. Check the output above.")

