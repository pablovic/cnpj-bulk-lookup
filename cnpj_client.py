import requests
import time
import re
import logging
import os
import pandas as pd
from typing import Optional

logging.basicConfig(
    filename='cnpj_lookup.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

BASE_URL = "https://publica.cnpj.ws/cnpj"

# ── All columns the app expects (error rows return all keys = empty string) ──
ALL_KEYS = [
    "cnpj", "razao_social", "nome_fantasia", "situacao_cadastral",
    "data_situacao_cadastral", "data_inicio_atividade", "cnpj_raiz", "tipo",
    "porte", "natureza_juridica", "capital_social",
    "pais", "estado", "estado_sigla", "cidade", "cep", "bairro",
    "tipo_logradouro", "logradouro", "numero", "complemento",
    "email", "telefone",
    "ie_uf", "ie_numero", "ie_lista",
    "simples_nacional", "mei", "socios",
    "codigo_municipio_completo",   # ← IBGE 7-digit code from municipios_lookup.csv
    "status", "error",
]

# ── Municipality lookup ───────────────────────────────────────────────────────
# Loaded ONCE at import time from municipios_lookup.csv (bundled with the app).
# Primary key: (NOME_UF_UPPER, NOME_MUNICIPIO_UPPER) → codigo_municipio_completo
# This handles the 232 city names that exist in multiple states.
_MUNICIPIO_LOOKUP: dict = {}

def _load_municipios() -> None:
    """
    Load municipios_lookup.csv from the same directory as this script.

    Expected layout:
        cnpj_bulk/
        ├── app.py
        ├── cnpj_client.py
        └── municipios_lookup.csv   ← columns: nome_uf_norm, nome_municipio_norm, codigo_municipio_completo
    """
    base_dir  = os.path.dirname(os.path.abspath(__file__))
    csv_path  = os.path.join(base_dir, "municipios_lookup.csv")

    if not os.path.exists(csv_path):
        logging.warning(f"Municipality file not found at: {csv_path}")
        return
    try:
        df = pd.read_csv(csv_path, dtype=str, encoding="utf-8")
        for _, row in df.iterrows():
            key = (row["nome_uf_norm"].strip(), row["nome_municipio_norm"].strip())
            _MUNICIPIO_LOOKUP[key] = row["codigo_municipio_completo"].strip()
        logging.info(f"Loaded {len(_MUNICIPIO_LOOKUP)} municipalities from CSV")
    except Exception as e:
        logging.error(f"Failed to load municipios_lookup.csv: {e}")

_load_municipios()


def lookup_codigo_municipio(estado_nome: str, cidade_nome: str) -> str:
    """
    Return the 7-digit IBGE Código Município Completo.
    Matches on (Nome_UF, Nome_Município) — both uppercase — to handle the
    232 city names that appear in more than one Brazilian state.
    Returns empty string if not found.
    """
    uf_key   = (estado_nome or "").upper().strip()
    city_key = (cidade_nome or "").upper().strip()
    if not uf_key or not city_key:
        return ""
    return _MUNICIPIO_LOOKUP.get((uf_key, city_key), "")


# ── Basic helpers ─────────────────────────────────────────────────────────────

def clean_cnpj(cnpj: str) -> str:
    return re.sub(r'\D', '', cnpj)


def validate_cnpj(cnpj: str) -> bool:
    return len(clean_cnpj(cnpj)) == 14


def format_cnpj(cnpj: str) -> str:
    c = clean_cnpj(cnpj)
    if len(c) == 14:
        return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"
    return cnpj


def empty_result(cnpj: str, status: str, error: str) -> dict:
    """Full-key dict with empty strings — prevents pandas KeyError on error rows."""
    base = {k: "" for k in ALL_KEYS}
    base["ie_lista"] = []
    base["cnpj"]   = cnpj
    base["status"] = status
    base["error"]  = error
    return base


# ── Main query function ───────────────────────────────────────────────────────

def get_cnpj_info(cnpj: str, api_key: Optional[str] = None, max_retries: int = 3) -> dict:
    """
    Query cnpj.ws for one CNPJ. Always returns a dict with ALL keys.
    Uses the commercial endpoint when api_key is provided.
    """
    cnpj_clean = clean_cnpj(cnpj)
    if not validate_cnpj(cnpj_clean):
        return empty_result(cnpj, "invalid", "Invalid CNPJ (must be 14 digits)")

    if api_key:
        url     = f"https://comercial.cnpj.ws/cnpj/{cnpj_clean}"
        headers = {"Accept": "application/json", "x_api_token": api_key}
    else:
        url     = f"{BASE_URL}/{cnpj_clean}"
        headers = {"Accept": "application/json"}

    formatted = format_cnpj(cnpj_clean)

    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=15)

            if response.status_code == 429:
                # Return a special status so the caller can display a countdown
                # and retry — we don't sleep here (would freeze the UI)
                retry_after = int(response.headers.get("Retry-After", 30))
                logging.warning(f"Rate limited on {cnpj} (attempt {attempt+1}). Retry-After={retry_after}s")
                return empty_result(formatted, "rate_limited", f"rate_limited:{retry_after}")
            if response.status_code == 404:
                return empty_result(formatted, "not_found", "CNPJ not found in database")
            if response.status_code == 401:
                return empty_result(formatted, "error", "Invalid API key (401 Unauthorized)")
            if response.status_code != 200:
                logging.warning(f"HTTP {response.status_code} for CNPJ {cnpj}")
                time.sleep(min(2 ** attempt, 8))
                continue

            return parse_cnpj_response(response.json(), cnpj_clean)

        except requests.exceptions.Timeout:
            logging.error(f"Timeout attempt {attempt+1} for {cnpj}")
            time.sleep(min(2 ** attempt, 8))
        except Exception as e:
            logging.error(f"Attempt {attempt+1} failed for {cnpj}: {e}")
            time.sleep(min(2 ** attempt, 8))

    return empty_result(formatted, "error", "Max retries reached")


# ── Response parser ───────────────────────────────────────────────────────────

def parse_cnpj_response(data: dict, cnpj_clean: str) -> dict:
    """
    Flatten the cnpj.ws JSON into a single dict.

    Phone numbers come as FLAT fields on estabelecimento (ddd1/telefone1, ddd2/telefone2),
    NOT as a nested telefones[] array.
    Email is also a plain string field, not an array.
    tipo_logradouro is a plain string (e.g. "RUA"), not an object.
    """
    estab    = data.get("estabelecimento") or {}
    porte    = data.get("porte")            or {}
    natureza = data.get("natureza_juridica") or {}
    simples  = data.get("simples")          or {}

    # Nested location objects
    pais   = estab.get("pais")   or {}
    estado = estab.get("estado") or {}
    cidade = estab.get("cidade") or {}

    estado_nome = estado.get("nome", "") or ""
    estado_sigla = estado.get("sigla", "") or ""
    cidade_nome  = cidade.get("nome", "") or ""

    # tipo_logradouro — plain string in this API, not an object
    tipo_logradouro_raw = estab.get("tipo_logradouro") or ""
    tipo_logradouro_str = (
        tipo_logradouro_raw.get("descricao", "") if isinstance(tipo_logradouro_raw, dict)
        else str(tipo_logradouro_raw)
    )

    # ── Phones — flat fields, NOT a nested array ──────────────────────────────
    phones = []
    ddd1, tel1 = estab.get("ddd1") or "", estab.get("telefone1") or ""
    ddd2, tel2 = estab.get("ddd2") or "", estab.get("telefone2") or ""
    if tel1:
        phones.append(f"({ddd1}) {tel1}" if ddd1 else tel1)
    if tel2:
        phones.append(f"({ddd2}) {tel2}" if ddd2 else tel2)

    # ── State registrations (IE) ──────────────────────────────────────────────
    inscricoes = estab.get("inscricoes_estaduais") or []
    ie_list = [
        {
            "uf":       (ie.get("estado") or {}).get("sigla", ""),
            "inscricao": ie.get("inscricao_estadual", ""),
            "ativo":     ie.get("ativo", ""),
        }
        for ie in inscricoes
    ]
    # Prefer first ACTIVE IE for flat columns
    active_ie = [ie for ie in ie_list if ie.get("ativo") is True]
    first_ie  = (active_ie or ie_list or [{}])[0]

    # ── Município code lookup ─────────────────────────────────────────────────
    # Joins API's estado.nome + cidade.nome against IBGE 2024 table.
    # Uses (Nome_UF, Nome_Município) to resolve cities that share names across states.
    codigo_municipio = lookup_codigo_municipio(estado_nome, cidade_nome)

    # ── Socios ────────────────────────────────────────────────────────────────
    socios = data.get("socios") or []
    socios_str = "; ".join([s.get("nome", "") for s in socios])

    return {
        "cnpj":                    format_cnpj(cnpj_clean),
        "razao_social":            data.get("razao_social", "")  or "",
        "nome_fantasia":           estab.get("nome_fantasia", "") or "",
        "situacao_cadastral":      estab.get("situacao_cadastral", "") or "",
        "data_situacao_cadastral": estab.get("data_situacao_cadastral", "") or "",
        "data_inicio_atividade":   estab.get("data_inicio_atividade", "") or "",
        "cnpj_raiz":               data.get("cnpj_raiz", "") or "",
        "tipo":                    estab.get("tipo", "") or "",
        "porte":                   porte.get("descricao", "") or "",
        "natureza_juridica": (
            f"{natureza.get('id','')} - {natureza.get('descricao','')}" if natureza else ""
        ),
        "capital_social":          data.get("capital_social", "") or "",
        # Location
        "pais":                    pais.get("nome", "") or "",
        "estado":                  estado_nome,
        "estado_sigla":            estado_sigla,
        "cidade":                  cidade_nome,
        "cep":                     estab.get("cep", "") or "",
        "bairro":                  estab.get("bairro", "") or "",
        "tipo_logradouro":         tipo_logradouro_str,
        "logradouro":              estab.get("logradouro", "") or "",
        "numero":                  estab.get("numero", "") or "",
        "complemento":             estab.get("complemento", "") or "",
        # Contact
        "email":                   estab.get("email", "") or "",
        "telefone":                "; ".join(phones),
        # IE
        "ie_uf":                   first_ie.get("uf", ""),
        "ie_numero":               first_ie.get("inscricao", ""),
        "ie_lista":                ie_list,
        # Simples
        "simples_nacional":        simples.get("simples", "") or "",
        "mei":                     simples.get("mei", "") or "",
        # Socios
        "socios":                  socios_str,
        # IBGE municipality code — joined from DTB 2024 table
        "codigo_municipio_completo": codigo_municipio,
        "status": "success",
        "error":  "",
    }
