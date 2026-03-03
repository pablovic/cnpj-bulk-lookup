import streamlit as st
import pandas as pd
import time
import random
import io
from datetime import datetime
from cnpj_client import get_cnpj_info, clean_cnpj, validate_cnpj, format_cnpj, _MUNICIPIO_LOOKUP

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="CNPJ Bulk Lookup",
    page_icon="🇧🇷",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(135deg, #009c3b 0%, #002776 100%);
        padding: 1.5rem 2rem;
        border-radius: 12px;
        color: white;
        margin-bottom: 1.5rem;
    }
    .main-header h1 { margin: 0; font-size: 2rem; }
    .main-header p  { margin: 0.3rem 0 0; opacity: 0.85; font-size: 1rem; }

    .metric-card {
        background: #f8f9fa;
        border: 1px solid #e0e0e0;
        border-radius: 10px;
        padding: 1rem;
        text-align: center;
    }
    .metric-card .label { font-size: 0.8rem; color: #666; text-transform: uppercase; }
    .metric-card .value { font-size: 2rem; font-weight: 700; }

    .success  { color: #009c3b; }
    .error    { color: #d32f2f; }
    .warning  { color: #f59e0b; }

    .stProgress > div > div > div { background-color: #009c3b; }
    div[data-testid="stExpander"] { border: 1px solid #e0e0e0; border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="main-header">
    <h1>🇧🇷 CNPJ Bulk Lookup</h1>
    <p>Query up to 1,000 CNPJs at once using the cnpj.ws API — export results to Excel or CSV</p>
</div>
""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Settings")

    api_key = st.text_input(
        "API Key (optional)",
        type="password",
        help="Leave blank for the free tier (3 req/min). Add your key for higher limits."
    )

    st.subheader("Rate Limiting")
    delay_min = st.slider("Min delay between requests (s)", 0.3, 5.0, 0.8, 0.1)
    delay_max = st.slider("Max delay between requests (s)", 0.5, 10.0, 1.5, 0.1)
    max_retries = st.slider("Max retries per CNPJ", 1, 5, 3)
    st.caption("💡 Free tier: 0.8–1.5s is safe. Lower = faster but riskier.")

    st.markdown("---")
    st.subheader("📊 Export Columns")
    cols_options = [
        "cnpj", "razao_social", "nome_fantasia", "situacao_cadastral",
        "data_situacao_cadastral", "data_inicio_atividade", "tipo",
        "porte", "natureza_juridica", "capital_social",
        "pais", "estado", "estado_sigla", "cidade",
        "codigo_municipio_completo",
        "cep", "bairro", "logradouro", "numero", "complemento",
        "email", "telefone", "ie_uf", "ie_numero",
        "simples_nacional", "mei", "socios",
    ]
    selected_cols = st.multiselect(
        "Columns to export",
        options=cols_options,
        key="export_cols_v2",   # bump this key whenever you change the defaults
        default=[
            "cnpj", "razao_social", "nome_fantasia", "situacao_cadastral",
            "data_inicio_atividade", "tipo", "porte", "natureza_juridica",
            "capital_social", "estado", "cidade",
            "codigo_municipio_completo",
            "cep", "bairro", "logradouro", "numero", "email", "telefone",
            "ie_uf", "ie_numero",
        ]
    )

    st.markdown("---")
    # Show municipality lookup status so you can verify it loaded
    if len(_MUNICIPIO_LOOKUP) > 0:
        st.success(f"🗺️ Municipality lookup: **{len(_MUNICIPIO_LOOKUP):,}** cities loaded")
    else:
        st.error("⚠️ Municipality lookup NOT loaded — check dim_municipality folder")
    st.caption("Data source: [cnpj.ws](https://www.cnpj.ws) · Max data lag: 45 days")

# ── Input section ─────────────────────────────────────────────────────────────
st.subheader("📥 Input CNPJs")

input_tab, file_tab = st.tabs(["✏️ Paste CNPJs", "📁 Upload File"])

cnpj_list_raw = []

with input_tab:
    text_input = st.text_area(
        "One CNPJ per line (formatted or raw digits accepted)",
        placeholder="11.222.333/0001-81\n22333444000155\n33.444.555/0002-66",
        height=200,
    )
    if text_input.strip():
        cnpj_list_raw = [line.strip() for line in text_input.strip().splitlines() if line.strip()]

with file_tab:
    uploaded = st.file_uploader(
        "Upload CSV or TXT — one CNPJ per row, first column used",
        type=["csv", "txt"],
    )
    if uploaded:
        try:
            if uploaded.name.endswith(".csv"):
                df_up = pd.read_csv(uploaded, header=None, dtype=str)
                cnpj_list_raw = df_up.iloc[:, 0].dropna().astype(str).str.strip().tolist()
            else:
                content = uploaded.read().decode("utf-8")
                cnpj_list_raw = [l.strip() for l in content.splitlines() if l.strip()]
            st.success(f"✅ Loaded **{len(cnpj_list_raw)}** CNPJs from file")
        except Exception as e:
            st.error(f"Error reading file: {e}")

# ── Validation preview ────────────────────────────────────────────────────────
if cnpj_list_raw:
    valid   = [c for c in cnpj_list_raw if validate_cnpj(c)]
    invalid = [c for c in cnpj_list_raw if not validate_cnpj(c)]

    col1, col2, col3 = st.columns(3)
    col1.metric("Total CNPJs", len(cnpj_list_raw))
    col2.metric("✅ Valid", len(valid))
    col3.metric("❌ Invalid", len(invalid))

    if invalid:
        with st.expander(f"⚠️ {len(invalid)} invalid CNPJs (will be skipped)"):
            st.write(invalid[:50])

    # Estimate time
    avg_delay = (delay_min + delay_max) / 2
    est_seconds = len(valid) * avg_delay
    est_min = int(est_seconds // 60)
    est_sec = int(est_seconds % 60)
    est_fast = int(len(valid) * delay_min)
    st.info(
        f"⏱️ Estimated time for {len(valid)} CNPJs: "
        f"**{est_min}m {est_sec}s** avg · "
        f"as fast as **{est_fast//60}m {est_fast%60}s** at min delay"
    )

# ── Run button ────────────────────────────────────────────────────────────────
st.markdown("---")

if "results" not in st.session_state:
    st.session_state.results = []

run_col, stop_col = st.columns([3, 1])
run_btn  = run_col.button("🚀 Start Bulk Lookup", type="primary", disabled=not cnpj_list_raw)
stop_btn = stop_col.button("⏹ Stop", type="secondary")

if "running" not in st.session_state:
    st.session_state.running = False

if stop_btn:
    st.session_state.running = False

if run_btn and cnpj_list_raw:
    st.session_state.running = True
    st.session_state.results = []

    valid_cnpjs = [c for c in cnpj_list_raw if validate_cnpj(c)]
    total = len(valid_cnpjs)

    st.subheader("⏳ Processing...")
    progress_bar   = st.progress(0)
    status_text    = st.empty()
    live_table     = st.empty()
    metrics_holder = st.empty()

    success_count = 0
    error_count   = 0
    start_time    = datetime.now()

    rate_limit_count = 0
    request_times = []   # rolling window for req/s calculation

    i = 0
    while i < len(valid_cnpjs):
        if not st.session_state.running:
            st.warning("⏹ Processing stopped by user.")
            break

        cnpj = valid_cnpjs[i]
        elapsed_total = (datetime.now() - start_time).total_seconds()
        completed     = len(st.session_state.results)
        req_per_min   = round(completed / elapsed_total * 60, 1) if elapsed_total > 0 else 0

        status_text.markdown(
            f"Processing **{i+1}/{total}** → `{format_cnpj(cnpj)}` "
            f"| ✅ {success_count} | ❌ {error_count} | 🚦 {rate_limit_count} throttled"
            f" | ⚡ {req_per_min} req/min"
        )

        t0 = time.time()
        result = get_cnpj_info(cnpj, api_key=api_key or None, max_retries=max_retries)

        # ── Handle rate-limit: show countdown, wait, then RETRY same CNPJ ────
        if result.get("status") == "rate_limited":
            rate_limit_count += 1
            error_msg = result.get("error", "rate_limited:30")
            wait_secs = int(error_msg.split(":")[-1]) if ":" in error_msg else 30
            wait_secs = max(wait_secs, 15)   # never wait less than 15s
            for remaining in range(wait_secs, 0, -1):
                if not st.session_state.running:
                    break
                status_text.markdown(
                    f"🚦 Rate limited — retrying in **{remaining}s**… "
                    f"(throttled {rate_limit_count}x so far)"
                )
                time.sleep(1)
            # Retry same index (don't increment i)
            continue

        st.session_state.results.append(result)

        if result.get("status") == "success":
            success_count += 1
        else:
            error_count += 1

        # Update progress
        progress_bar.progress((i + 1) / total)

        # Live preview (last 5 rows)
        preview_df = pd.DataFrame(st.session_state.results[-5:]).reindex(
            columns=["cnpj", "razao_social", "situacao_cadastral", "status", "error"]
        )
        live_table.dataframe(preview_df, use_container_width=True)

        i += 1  # advance only on non-rate-limited results

        # ── Delay — skip entirely if this request errored (already slow) ─────
        if i < total and st.session_state.running:
            if result.get("status") in ("success", "not_found"):
                # Normal delay — random within the user's chosen range
                delay = delay_min + (delay_max - delay_min) * random.random()
                # If request itself was slow, subtract that time from the delay
                elapsed_req = time.time() - t0
                sleep_time  = max(0.0, delay - elapsed_req)
                if sleep_time > 0:
                    time.sleep(sleep_time)
            # On error: no extra delay — the retry backoff inside get_cnpj_info already waited

    st.session_state.running = False
    elapsed = (datetime.now() - start_time).seconds
    st.success(
        f"✅ Done! Processed **{len(st.session_state.results)}** CNPJs in "
        f"**{elapsed//60}m {elapsed%60}s** — "
        f"{success_count} success, {error_count} errors"
    )

# ── Results & Export ──────────────────────────────────────────────────────────
if st.session_state.results:
    st.markdown("---")
    st.subheader("📊 Results")

    df_results = pd.DataFrame(st.session_state.results)

    # Summary metrics
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Processed", len(df_results))
    m2.metric("✅ Success", (df_results["status"] == "success").sum())
    m3.metric("❌ Errors", (df_results["status"] != "success").sum())
    ativa_col = "situacao_cadastral"
    if ativa_col in df_results.columns:
        ativas = df_results[ativa_col].str.upper().str.contains("ATIVA", na=False).sum()
        m4.metric("🟢 Ativas", ativas)

    # Filter
    filter_status = st.selectbox("Filter by status", ["All", "success", "error", "not_found", "invalid", "rate_limited"])
    df_show = df_results if filter_status == "All" else df_results[df_results["status"] == filter_status]

    # Display columns
    display_cols = [c for c in selected_cols if c in df_show.columns] + ["status", "error"]
    display_cols = list(dict.fromkeys(display_cols))  # dedupe
    st.dataframe(df_show[display_cols], use_container_width=True, height=400)

    # Export
    st.subheader("💾 Export")
    exp1, exp2 = st.columns(2)

    with exp1:
        export_df = df_results[[c for c in selected_cols if c in df_results.columns] + ["status", "error"]]
        csv_bytes = export_df.to_csv(index=False, sep=";", encoding="utf-8-sig").encode("utf-8-sig")
        st.download_button(
            "⬇️ Download CSV",
            data=csv_bytes,
            file_name=f"cnpj_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
        )

    with exp2:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            export_df.to_excel(writer, index=False, sheet_name="Results")
            # Errors on second sheet
            df_errors = df_results[df_results["status"] != "success"][["cnpj", "status", "error"]]
            if not df_errors.empty:
                df_errors.to_excel(writer, index=False, sheet_name="Errors")
        output.seek(0)
        st.download_button(
            "⬇️ Download Excel",
            data=output.getvalue(),
            file_name=f"cnpj_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    # Errors detail
    df_err = df_results[df_results["status"] != "success"]
    if not df_err.empty:
        with st.expander(f"❌ {len(df_err)} failed CNPJs"):
            st.dataframe(df_err[["cnpj", "status", "error"]], use_container_width=True)

    if st.button("🗑️ Clear Results"):
        st.session_state.results = []
        st.rerun()
