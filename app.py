import math
from io import BytesIO
from pathlib import Path
from typing import Optional, Tuple, Union
from urllib.request import urlopen

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ============================================================
# Konfigurasi halaman
# ============================================================
st.set_page_config(
    page_title="Dashboard Pemantauan PDB",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

REPO_FILE_NAME = "dashboard PDB.xlsx"
try:
    GITHUB_RAW_XLSX_URL = st.secrets.get("github_raw_xlsx_url", "")
except Exception:
    GITHUB_RAW_XLSX_URL = ""

PRIMARY = "#3E6DB5"
ACCENT = "#E07B39"
SUCCESS = "#2A9D8F"
PURPLE = "#8A5CF6"
NEGATIVE = "#D14D72"
BG = "#F6F7FB"
TEXT = "#1F2937"
GRID = "rgba(31,41,55,0.12)"

PERIOD_MAP = {
    "out_tw1": "Outlook Q1",
    "out_tw2": "Outlook Q2",
    "out_tw3": "Outlook Q3",
    "out_tw4": "Outlook Q4",
    "full_year": "Full Year",
}
PERIOD_ORDER = list(PERIOD_MAP.keys())

# PDB Aggregate tidak lagi dibaca dari Excel.
# Komponen ini selalu dihitung internal dari komponen pembentuknya.
PDB_COMPONENTS = [
    "Konsumsi RT",
    "Konsumsi LNPRT",
    "PKP",
    "PMTB",
    "Change in Stocks",
    "Ekspor",
    "Impor",
    "PDB Aggregate",
]
PDB_AGGREGATE_INPUTS = [
    "Konsumsi RT",
    "Konsumsi LNPRT",
    "PKP",
    "PMTB",
    "Change in Stocks",
    "Ekspor",
    "Impor",
]
PDB_MAIN_HIDE = ["Konsumsi LNPRT", "Change in Stocks"]
EXCLUDE_GROWTH_ROWS = ["Change in Stocks"]

EXPECTED_SHEETS = {
    "simulasi": ["indikator", *PERIOD_ORDER],
    "makro": ["indikator", *PERIOD_ORDER],
    "pdb": ["indikator", *PERIOD_ORDER],
    "moneter": ["indikator", *PERIOD_ORDER],
    "fiskal": ["indikator", *PERIOD_ORDER],
}

DEFAULT_ROWS = {
    "simulasi": ["Consumption", "Investment", "Govt. Spending", "Export", "Import", "Unemployment"],
    "makro": ["Inflasi", "Rupiah", "Yield SBN", "ICP", "Nikel", "Coal", "CPO", "Lifting"],
    "pdb": PDB_COMPONENTS,
    "moneter": ["PUAB", "Kredit", "DPK", "M0", "OMO"],
    "fiskal": ["Pendapatan", "Belanja", "Pembiayaan", "Defisit"],
}

BLOCK_TITLES = {
    "makro": "Blok Makro",
    "pdb": "Blok Accounting",
    "moneter": "Blok Moneter",
    "fiskal": "Blok Fiskal",
}

BLOCK_NOTES = {
    "makro": "Indikator makro.",
    "pdb": "Nominal dan pertumbuhan PDB 2026 diturunkan langsung dari sheet realisasi.",
    "moneter": "Variabel moneter.",
    "fiskal": "I-Account APBN.",
}

SIMULASI_FISKAL_ROWS = [
    "Bantuan Pangan",
    "Bantuan Langsung Tunai",
    "Kenaikan Gaji",
    "Pembayaran Gaji 14",
    "Diskon Transportasi",
    "Investasi",
]
SIMULASI_FISKAL_COLS = ["out_tw1", "out_tw2", "out_tw3", "out_tw4"]

st.markdown(
    f"""
    <style>
        .main {{ background-color: {BG}; }}
        .block-title {{ font-size: 1.05rem; font-weight: 700; color: {TEXT}; margin: 0.15rem 0 0.35rem 0; }}
        .sub-title {{ font-size: 0.95rem; font-weight: 700; color: {TEXT}; margin: 0.2rem 0 0.35rem 0; }}
        .section-note {{ color: #6B7280; font-size: 0.88rem; margin-bottom: 0.45rem; }}
        .status-box {{ border: 1px dashed rgba(62,109,181,0.30); border-radius: 12px; padding: 0.55rem 0.75rem; background: rgba(62,109,181,0.03); color: #374151; margin-bottom: 0.75rem; font-size: 0.86rem; }}
        .fiscal-editor-header {{ display:block; margin-top:0.35rem; margin-bottom:0.25rem; }}
        .fiscal-editor-title {{ color: {PRIMARY}; font-size: 1.02rem; font-weight: 700; display:inline; }}
        .fiscal-editor-unit {{ color: #111827; font-size: 0.92rem; display:inline; margin-left: 0.35rem; }}
        div[data-testid="stDataEditor"] * {{ font-size: 0.95rem !important; }}
        div[data-testid="stDataFrame"] * {{ font-size: 0.94rem !important; }}
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# Utilitas umum
# ============================================================
def normalize_key(text: object) -> str:
    return str(text).strip().lower().replace(" ", "_").replace(".", "").replace("-", "_")


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    mapper = {c: normalize_key(c) for c in df.columns}
    return df.rename(columns=mapper).copy()


def empty_df(block: str) -> pd.DataFrame:
    rows = DEFAULT_ROWS[block]
    payload = {"indikator": rows}
    for col in PERIOD_ORDER:
        payload[col] = [None] * len(rows)
    return pd.DataFrame(payload)


def ensure_indicator_rows(df: pd.DataFrame, block: str) -> pd.DataFrame:
    expected_rows = DEFAULT_ROWS.get(block, [])
    if not expected_rows or "indikator" not in df.columns:
        return df
    work = df.copy()
    work["indikator"] = work["indikator"].fillna("").astype(str).str.strip()
    numeric_cols = [c for c in work.columns if c != "indikator"]
    out_rows = []
    for ind in expected_rows:
        found = work.loc[work["indikator"] == ind]
        if not found.empty:
            out_rows.append(found.iloc[0].to_dict())
        else:
            row = {"indikator": ind}
            for c in numeric_cols:
                row[c] = None
            out_rows.append(row)
    return pd.DataFrame(out_rows)


def coerce_schema(df: pd.DataFrame, block: str) -> pd.DataFrame:
    df = normalize_columns(df)
    expected = EXPECTED_SHEETS[block]
    if "indikator" not in df.columns and len(df.columns) > 0:
        df = df.rename(columns={df.columns[0]: "indikator"})
    for col in expected:
        if col not in df.columns:
            df[col] = None
    df = df[expected].copy()
    return ensure_indicator_rows(df, block)


def _format_id_number(val: float, decimals: int = 0) -> str:
    s = f"{float(val):,.{decimals}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_id0(val):
    if pd.isna(val) or val is None:
        return "—"
    try:
        return _format_id_number(val, 0)
    except Exception:
        return str(val)


def fmt_pct_id2(val):
    if pd.isna(val) or val is None:
        return "—"
    try:
        return _format_id_number(val, 2) + "%"
    except Exception:
        return str(val)


def make_tick_values(series: pd.Series, n: int = 6):
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty:
        return [], []
    vmin = float(s.min())
    vmax = float(s.max())
    if math.isclose(vmin, vmax):
        vals = [0] if math.isclose(vmin, 0.0) else [vmin - abs(vmin) * 0.1, vmin, vmin + abs(vmin) * 0.1]
    else:
        step = (vmax - vmin) / max(n - 1, 1)
        vals = [vmin + i * step for i in range(n)]
    return vals, [fmt_id0(v) for v in vals]


def make_tick_values_pct(series: pd.Series, n: int = 6):
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty:
        return [], []
    vmin = float(s.min())
    vmax = float(s.max())
    base_min = min(vmin, 0.0)
    base_max = max(vmax, 0.0)
    if math.isclose(base_min, base_max):
        vals = [base_min - 1, base_min, base_min + 1]
    else:
        step = (base_max - base_min) / max(n - 1, 1)
        vals = [base_min + i * step for i in range(n)]
    return vals, [fmt_pct_id2(v) for v in vals]


def filter_growth_rows(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return empty_df("pdb")
    return df[~df["indikator"].isin(EXCLUDE_GROWTH_ROWS)].copy()


def filter_growth_components(components: list[str]) -> list[str]:
    return [c for c in components if c not in EXCLUDE_GROWTH_ROWS]


def filter_main_pdb_rows(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return empty_df("pdb")
    return df[~df["indikator"].isin(PDB_MAIN_HIDE)].copy()


def ensure_full_year_from_quarters(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return empty_df("pdb")
    work = df.copy()
    q_cols = ["out_tw1", "out_tw2", "out_tw3", "out_tw4"]
    for col in q_cols:
        if col not in work.columns:
            work[col] = None
        work[col] = pd.to_numeric(work[col], errors="coerce")
    work["full_year"] = work[q_cols].sum(axis=1, min_count=1)
    return work


def choose_realisasi_column(columns: list[str], target: str) -> Optional[str]:
    target_norm = normalize_key(target)
    for col in columns:
        if normalize_key(col) == target_norm:
            return col
    return None


# ============================================================
# Excel source
# ============================================================
def load_excel_bytes_from_url(url: str) -> bytes:
    with urlopen(url) as response:
        return response.read()


def open_excel_source(source: Union[str, bytes, bytearray]):
    if isinstance(source, (bytes, bytearray)):
        return pd.ExcelFile(BytesIO(source), engine="openpyxl")
    return pd.ExcelFile(source, engine="openpyxl")


def detect_excel_source() -> Tuple[Optional[Union[str, bytes]], str]:
    local_path = Path(__file__).resolve().parent / REPO_FILE_NAME
    if local_path.exists():
        return str(local_path), f"Sumber data otomatis: file lokal {REPO_FILE_NAME}"
    if GITHUB_RAW_XLSX_URL:
        return load_excel_bytes_from_url(GITHUB_RAW_XLSX_URL), "Sumber data otomatis: GitHub Raw URL dari st.secrets['github_raw_xlsx_url']"
    return None, (
        "File Excel belum ditemukan. Simpan dashboard PDB.xlsx di folder yang sama dengan app.py, "
        "atau isi st.secrets['github_raw_xlsx_url']."
    )


# ============================================================
# Turunan PDB dari sheet realisasi
# ============================================================
def _build_period_table_from_series_map(df: pd.DataFrame, row_map: dict[str, str]) -> pd.DataFrame:
    out = []
    for indikator, source_col in row_map.items():
        row_df = df[["tanggal", source_col]].copy().sort_values("tanggal")
        row_df["tahun"] = row_df["tanggal"].dt.year
        row_df["quarter"] = row_df["tanggal"].dt.quarter
        row_2026 = row_df[row_df["tahun"] == 2026].copy()
        quarter_values = {}
        for q in [1, 2, 3, 4]:
            sel = row_2026.loc[row_2026["quarter"] == q, source_col]
            quarter_values[f"out_tw{q}"] = float(sel.iloc[-1]) if not sel.empty else None
        fy = sum(v for v in quarter_values.values() if v is not None) if any(v is not None for v in quarter_values.values()) else None
        out.append({"indikator": indikator, **quarter_values, "full_year": fy})
    return pd.DataFrame(out)


def _build_growth_table(level_df: pd.DataFrame, periods: int, growth_name: str) -> pd.DataFrame:
    out_rows = []
    for indikator in PDB_COMPONENTS:
        s = level_df[["tanggal", indikator]].copy().sort_values("tanggal")
        s[growth_name] = s[indikator].pct_change(periods=periods) * 100
        s["tahun"] = s["tanggal"].dt.year
        s["quarter"] = s["tanggal"].dt.quarter
        s_2026 = s[s["tahun"] == 2026].copy()
        quarter_values = {}
        for q in [1, 2, 3, 4]:
            sel = s_2026.loc[s_2026["quarter"] == q, growth_name]
            quarter_values[f"out_tw{q}"] = float(sel.iloc[-1]) if not sel.empty else None
        annual = s.assign(yearly_sum=s.groupby("tahun")[indikator].transform("sum"))[["tahun", "yearly_sum"]].drop_duplicates().sort_values("tahun")
        annual[growth_name] = annual["yearly_sum"].pct_change(periods=1) * 100
        annual_2026 = annual.loc[annual["tahun"] == 2026, growth_name]
        full_year = float(annual_2026.iloc[-1]) if not annual_2026.empty else None
        out_rows.append({"indikator": indikator, **quarter_values, "full_year": full_year})
    return pd.DataFrame(out_rows)


def derive_pdb_from_realisasi(source: Union[str, bytes]):
    xls = open_excel_source(source)
    sheet_map = {s.lower().strip(): s for s in xls.sheet_names}
    if "realisasi" not in sheet_map:
        return empty_df("pdb"), None, None, None

    raw = pd.read_excel(xls, sheet_name=sheet_map["realisasi"], engine="openpyxl")
    raw = raw.rename(columns={raw.columns[0]: "tanggal"}).copy()
    raw["tanggal"] = pd.to_datetime(raw["tanggal"], errors="coerce")
    raw = raw.dropna(subset=["tanggal"]).sort_values("tanggal").reset_index(drop=True)

    alias_map = {
        "Konsumsi RT": ["Konsumsi_RT"],
        "Konsumsi LNPRT": ["Konsumsi_LNPRT"],
        "PKP": ["PKP"],
        "PMTB": ["PMTB"],
        "Change in Stocks": ["Change_in_Stocks"],
        "Ekspor": ["Ekspor"],
        "Impor": ["Impor"],
    }

    mapping = {}
    for indikator in PDB_AGGREGATE_INPUTS:
        source_col = choose_realisasi_column(list(raw.columns), indikator)
        if source_col is None:
            for alias in alias_map.get(indikator, []):
                source_col = choose_realisasi_column(list(raw.columns), alias)
                if source_col is not None:
                    break
        if source_col is not None:
            mapping[indikator] = source_col

    level_df = raw[["tanggal", *mapping.values()]].copy().rename(columns={v: k for k, v in mapping.items()})
    for indikator in PDB_AGGREGATE_INPUTS:
        if indikator not in level_df.columns:
            level_df[indikator] = None
        level_df[indikator] = pd.to_numeric(level_df[indikator], errors="coerce")

    # PDB Aggregate selalu dihitung internal dari komponen yang ada.
    level_df["PDB Aggregate"] = (
        level_df["Konsumsi RT"].fillna(0)
        + level_df["Konsumsi LNPRT"].fillna(0)
        + level_df["PKP"].fillna(0)
        + level_df["PMTB"].fillna(0)
        + level_df["Change in Stocks"].fillna(0)
        + level_df["Ekspor"].fillna(0)
        - level_df["Impor"].fillna(0)
    )

    level_df = level_df[["tanggal", *PDB_COMPONENTS]].copy()
    nominal_table = coerce_schema(_build_period_table_from_series_map(level_df, {k: k for k in PDB_COMPONENTS}), "pdb")
    nominal_table = ensure_full_year_from_quarters(nominal_table)
    yoy_table = coerce_schema(_build_growth_table(level_df, periods=4, growth_name="yoy"), "pdb")
    qtq_table = coerce_schema(_build_growth_table(level_df, periods=1, growth_name="qtq"), "pdb")

    level_long = level_df.melt(id_vars=["tanggal"], value_vars=PDB_COMPONENTS, var_name="komponen", value_name="nilai")
    level_long["nilai_fmt"] = level_long["nilai"].apply(fmt_id0)

    growth_long = []
    for indikator in PDB_COMPONENTS:
        s = level_df[["tanggal", indikator]].copy().sort_values("tanggal")
        s["yoy"] = s[indikator].pct_change(periods=4) * 100
        s["qtq"] = s[indikator].pct_change(periods=1) * 100
        s["komponen"] = indikator
        growth_long.append(s[["tanggal", "komponen", "yoy", "qtq"]])
    growth_long = pd.concat(growth_long, ignore_index=True)

    pdb_history = {"level": level_long, "growth": growth_long}
    pdb_tables = {"yoy": yoy_table, "qtq": qtq_table}
    return nominal_table, pdb_history, pdb_tables, level_df


# ============================================================
# Loading dashboard data
# ============================================================
def load_dashboard_data():
    data = {k: empty_df(k) for k in EXPECTED_SHEETS.keys()}
    pdb_history = None
    pdb_tables = None
    source, source_status = detect_excel_source()
    if source is None:
        return data, pdb_history, pdb_tables, source_status

    try:
        xls = open_excel_source(source)
        lower_sheet_map = {s.lower().strip(): s for s in xls.sheet_names}

        for block in ["simulasi", "makro", "moneter", "fiskal"]:
            if block in lower_sheet_map:
                df = pd.read_excel(xls, sheet_name=lower_sheet_map[block], engine="openpyxl")
                data[block] = coerce_schema(df, block)

        if "realisasi" in lower_sheet_map:
            data["pdb"], pdb_history, pdb_tables, _ = derive_pdb_from_realisasi(source)
        elif "pdb" in lower_sheet_map:
            df = pd.read_excel(xls, sheet_name=lower_sheet_map["pdb"], engine="openpyxl")
            data["pdb"] = ensure_full_year_from_quarters(coerce_schema(df, "pdb"))

        return data, pdb_history, pdb_tables, source_status
    except Exception as e:
        return data, pdb_history, pdb_tables, f"Gagal membaca sumber Excel otomatis: {e}"


# ============================================================
# Render tabel dan chart
# ============================================================
def block_card(title: str, note: Optional[str] = None):
    st.markdown(f'<div class="block-title">{title}</div>', unsafe_allow_html=True)
    if note:
        st.markdown(f'<div class="section-note">{note}</div>', unsafe_allow_html=True)


def sub_title(text: str):
    st.markdown(f'<div class="sub-title">{text}</div>', unsafe_allow_html=True)


def format_display(df: pd.DataFrame, value_formatter=fmt_id0) -> pd.DataFrame:
    view = df.copy()
    ordered_cols = ["indikator", *PERIOD_ORDER]
    for c in ordered_cols:
        if c not in view.columns:
            view[c] = None
    view = view[ordered_cols].rename(columns={"indikator": "Indikator", **PERIOD_MAP})
    for c in view.columns[1:]:
        view[c] = view[c].apply(value_formatter)
    return view.fillna("—")


def render_table_block(block_df: pd.DataFrame, block_key: str = ""):
    view = format_display(block_df, value_formatter=fmt_id0)
    st.dataframe(
        view,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Indikator": st.column_config.TextColumn("Indikator", width="large"),
            "Outlook Q1": st.column_config.TextColumn("Outlook Q1", width="small"),
            "Outlook Q2": st.column_config.TextColumn("Outlook Q2", width="small"),
            "Outlook Q3": st.column_config.TextColumn("Outlook Q3", width="small"),
            "Outlook Q4": st.column_config.TextColumn("Outlook Q4", width="small"),
            "Full Year": st.column_config.TextColumn("Full Year", width="small"),
        },
        height=315 if block_key == "simulasi" else 340,
    )


def render_growth_table(df: pd.DataFrame, title: str):
    sub_title(title)
    view = format_display(filter_growth_rows(df), value_formatter=fmt_pct_id2)
    st.dataframe(
        view,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Indikator": st.column_config.TextColumn("Indikator", width="large"),
            "Outlook Q1": st.column_config.TextColumn("Outlook Q1", width="small"),
            "Outlook Q2": st.column_config.TextColumn("Outlook Q2", width="small"),
            "Outlook Q3": st.column_config.TextColumn("Outlook Q3", width="small"),
            "Outlook Q4": st.column_config.TextColumn("Outlook Q4", width="small"),
            "Full Year": st.column_config.TextColumn("Full Year", width="small"),
        },
        height=300,
    )


def placeholder_chart(msg: str, height: int = 380):
    fig = go.Figure()
    fig.add_annotation(text=msg, x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False, font=dict(size=14, color="#6B7280"))
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=40, b=10), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


def make_pdb_history_chart(pdb_history: Optional[dict], selected_components: list[str]):
    if not pdb_history or pdb_history.get("level") is None or pdb_history["level"].empty:
        return placeholder_chart("Data historis PDB belum tersedia pada sumber Excel.")
    plot_df = pdb_history["level"].copy()
    plot_df = plot_df[plot_df["komponen"].isin(selected_components)]
    if plot_df.empty:
        return placeholder_chart("Komponen historis yang dipilih belum memiliki data.")
    fig = px.line(
        plot_df,
        x="tanggal",
        y="nilai",
        color="komponen",
        color_discrete_sequence=[PRIMARY, ACCENT, SUCCESS, PURPLE, NEGATIVE, "#F4A261", "#4C78A8", "#6C8EAD"],
        custom_data=["nilai_fmt"],
    )
    fig.update_traces(mode="lines+markers", line=dict(width=2.6), marker=dict(size=5.5), hovertemplate="<b>%{fullData.name}</b><br>%{x|%Y-%m-%d}: %{customdata[0]}<extra></extra>")
    tickvals, ticktext = make_tick_values(plot_df["nilai"])
    fig.update_layout(title="Historis Komponen PDB", height=395, margin=dict(l=10, r=10, t=50, b=10), hovermode="x unified", legend_title_text="Komponen", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=True, gridcolor=GRID, zeroline=False, tickmode="array", tickvals=tickvals, ticktext=ticktext)
    return fig


def make_growth_chart(pdb_history: Optional[dict], selected_components: list[str], growth_col: str, title: str, colors=None):
    if not pdb_history or pdb_history.get("growth") is None or pdb_history["growth"].empty:
        return placeholder_chart("Data pertumbuhan PDB belum tersedia pada sumber Excel.")
    plot_df = pdb_history["growth"].copy()
    plot_df = plot_df[plot_df["komponen"].isin(selected_components)]
    if plot_df.empty:
        return placeholder_chart("Komponen pertumbuhan yang dipilih belum memiliki data.")
    plot_df["nilai_fmt"] = plot_df[growth_col].apply(fmt_pct_id2)
    fig = px.line(
        plot_df,
        x="tanggal",
        y=growth_col,
        color="komponen",
        color_discrete_sequence=colors or [PRIMARY, ACCENT, SUCCESS, PURPLE, NEGATIVE, "#F4A261", "#4C78A8", "#6C8EAD"],
        custom_data=["nilai_fmt"],
    )
    fig.update_traces(mode="lines+markers", line=dict(width=2.4), marker=dict(size=5.0), hovertemplate="<b>%{fullData.name}</b><br>%{x|%Y-%m-%d}: %{customdata[0]}<extra></extra>")
    tickvals, ticktext = make_tick_values_pct(plot_df[growth_col])
    fig.update_layout(title=title, height=395, margin=dict(l=10, r=10, t=50, b=10), hovermode="x unified", legend_title_text="Komponen", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=True, gridcolor=GRID, zeroline=True, tickmode="array", tickvals=tickvals, ticktext=ticktext)
    return fig


# ============================================================
# Simulasi fiskal editor
# ============================================================
def build_simulasi_fiskal_df() -> pd.DataFrame:
    return pd.DataFrame({
        "indikator": SIMULASI_FISKAL_ROWS,
        "out_tw1": [0.0] * len(SIMULASI_FISKAL_ROWS),
        "out_tw2": [0.0] * len(SIMULASI_FISKAL_ROWS),
        "out_tw3": [0.0] * len(SIMULASI_FISKAL_ROWS),
        "out_tw4": [0.0] * len(SIMULASI_FISKAL_ROWS),
    })


def get_simulasi_fiskal_df() -> pd.DataFrame:
    if "simulasi_fiskal_df" not in st.session_state:
        st.session_state["simulasi_fiskal_df"] = build_simulasi_fiskal_df()
    df = st.session_state["simulasi_fiskal_df"].copy()
    for col in ["indikator", *SIMULASI_FISKAL_COLS]:
        if col not in df.columns:
            df[col] = SIMULASI_FISKAL_ROWS if col == "indikator" else 0.0
    df = df[["indikator", *SIMULASI_FISKAL_COLS]].copy()
    df["indikator"] = SIMULASI_FISKAL_ROWS
    for col in SIMULASI_FISKAL_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    st.session_state["simulasi_fiskal_df"] = df
    return df


def render_simulasi_fiskal_editor() -> pd.DataFrame:
    st.markdown('<div class="fiscal-editor-header"><span class="fiscal-editor-title">SIMULASI FISKAL</span><span class="fiscal-editor-unit">(dalam Miliar)</span></div>', unsafe_allow_html=True)
    df = get_simulasi_fiskal_df()
    edited_df = st.data_editor(
        df,
        key="simulasi_fiskal_editor",
        hide_index=True,
        use_container_width=False,
        width=760,
        num_rows="fixed",
        disabled=["indikator"],
        column_config={
            "indikator": st.column_config.TextColumn("SIMULASI FISKAL", width="medium"),
            "out_tw1": st.column_config.NumberColumn("Q1", format="%.2f", step=0.01, width="small"),
            "out_tw2": st.column_config.NumberColumn("Q2", format="%.2f", step=0.01, width="small"),
            "out_tw3": st.column_config.NumberColumn("Q3", format="%.2f", step=0.01, width="small"),
            "out_tw4": st.column_config.NumberColumn("Q4", format="%.2f", step=0.01, width="small"),
        },
    )
    edited_df = edited_df[["indikator", *SIMULASI_FISKAL_COLS]].copy()
    edited_df["indikator"] = SIMULASI_FISKAL_ROWS
    for col in SIMULASI_FISKAL_COLS:
        edited_df[col] = pd.to_numeric(edited_df[col], errors="coerce").fillna(0.0)
    st.session_state["simulasi_fiskal_df"] = edited_df
    return edited_df


# ============================================================
# App
# ============================================================
workbook, pdb_history, pdb_tables, source_status = load_dashboard_data()
simulasi_fiskal_df = get_simulasi_fiskal_df()

st.sidebar.markdown("## Pengaturan Dashboard")
show_preview = st.sidebar.toggle("Tampilkan preview data mentah", value=False)
st.sidebar.markdown("### Sumber Data")
st.sidebar.info(source_status)

st.title("Dashboard Pemantauan PDB")
st.markdown("---")
st.markdown(f"<div class='status-box'>{source_status}</div>", unsafe_allow_html=True)

block_card("Tabel Utama — Blok Accounting (Nominal 2026)", BLOCK_NOTES["pdb"])
render_table_block(filter_main_pdb_rows(ensure_full_year_from_quarters(workbook["pdb"])), block_key="pdb")
simulasi_fiskal_df = render_simulasi_fiskal_editor()


tab_makro, tab_pdb, tab_moneter, tab_fiskal = st.tabs(["Blok Makro", "Blok Accounting", "Blok Moneter", "Blok Fiskal"])

with tab_makro:
    block_card(BLOCK_TITLES["makro"], BLOCK_NOTES["makro"])
    render_table_block(workbook["makro"], block_key="makro")

with tab_pdb:
    block_card(BLOCK_TITLES["pdb"], BLOCK_NOTES["pdb"])
    nominal_tab, yoy_tab, qtq_tab = st.tabs(["Tabel Nominal 2026", "Tabel Year on Year (YoY)", "Tabel Quarter to Quarter (QtQ)"])
    with nominal_tab:
        sub_title("Tabel Nominal 2026")
        render_table_block(ensure_full_year_from_quarters(workbook["pdb"]), block_key="pdb")
    with yoy_tab:
        render_growth_table(
            pdb_tables.get("yoy", empty_df("pdb")) if pdb_tables is not None else empty_df("pdb"),
            "Tabel Year on Year (YoY)",
        )
    with qtq_tab:
        render_growth_table(
            pdb_tables.get("qtq", empty_df("pdb")) if pdb_tables is not None else empty_df("pdb"),
            "Tabel Quarter to Quarter (QtQ)",
        )

    st.markdown("<div style='height:0.15rem'></div>", unsafe_allow_html=True)
    selected_components = st.multiselect(
        "Pilih komponen historis yang ingin ditampilkan",
        options=PDB_COMPONENTS,
        default=PDB_COMPONENTS,
        key="hist_components_pdb",
    )
    selected_components = selected_components or PDB_COMPONENTS
    selected_growth_components = filter_growth_components(selected_components)
    ch1, ch2, ch3 = st.tabs(["Historis Level", "Year on Year (YoY)", "Quarter to Quarter (QtQ)"])
    with ch1:
        st.plotly_chart(make_pdb_history_chart(pdb_history, selected_components), use_container_width=True)
    with ch2:
        st.plotly_chart(make_growth_chart(pdb_history, selected_growth_components, "yoy", "Pertumbuhan Year on Year (YoY)", colors=[SUCCESS, ACCENT, PRIMARY, PURPLE, NEGATIVE, "#F4A261", "#4C78A8", "#6C8EAD"]), use_container_width=True)
    with ch3:
        st.plotly_chart(make_growth_chart(pdb_history, selected_growth_components, "qtq", "Pertumbuhan Quarter to Quarter (QtQ)", colors=[PURPLE, SUCCESS, PRIMARY, ACCENT, NEGATIVE, "#F4A261", "#4C78A8", "#6C8EAD"]), use_container_width=True)

with tab_moneter:
    block_card(BLOCK_TITLES["moneter"], BLOCK_NOTES["moneter"])
    render_table_block(workbook["moneter"], block_key="moneter")

with tab_fiskal:
    block_card(BLOCK_TITLES["fiskal"], BLOCK_NOTES["fiskal"])
    render_table_block(workbook["fiskal"], block_key="fiskal")

with st.expander("Lihat struktur sumber Excel"):
    info = pd.DataFrame({
        "Sumber": [REPO_FILE_NAME, "st.secrets['github_raw_xlsx_url'] (opsional)"],
        "Keterangan": [
            "File diletakkan di folder yang sama dengan app.py sehingga otomatis terbaca saat deploy Streamlit dari GitHub.",
            "Dipakai hanya bila file Excel tidak diletakkan langsung di repo lokal.",
        ],
    })
    st.dataframe(info, use_container_width=True, hide_index=True)

if show_preview:
    with st.expander("Preview data yang berhasil dimuat", expanded=False):
        tab_names = ["Simulasi", "Makro", "PDB Nominal", "PDB YoY", "PDB QtQ", "Moneter", "Fiskal"]
        tabs = st.tabs(tab_names)
        preview_keys = [
            workbook["simulasi"],
            workbook["makro"],
            ensure_full_year_from_quarters(workbook["pdb"]),
            filter_growth_rows(pdb_tables.get("yoy", empty_df("pdb"))) if pdb_tables else empty_df("pdb"),
            filter_growth_rows(pdb_tables.get("qtq", empty_df("pdb"))) if pdb_tables else empty_df("pdb"),
            workbook["moneter"],
            workbook["fiskal"],
        ]
        for tab, df in zip(tabs, preview_keys):
            with tab:
                st.dataframe(df, use_container_width=True, hide_index=True)
        st.markdown("### Preview simulasi fiskal editable")
        st.dataframe(simulasi_fiskal_df, use_container_width=True, hide_index=True)
        if pdb_history is not None:
            st.markdown("### Preview historis komponen PDB")
            st.dataframe(pdb_history["level"], use_container_width=True, hide_index=True)
            st.markdown("### Preview pertumbuhan komponen PDB")
            st.dataframe(pdb_history["growth"], use_container_width=True, hide_index=True)
