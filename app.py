import math
import html
import textwrap
from io import BytesIO
from pathlib import Path
from typing import Optional, Tuple, Union
from urllib.request import urlopen

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(
    page_title="Dashboard Pemantauan PDB",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------- Konfigurasi ----------
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
POS_LIGHT = "#DCEFEA"
NEG_LIGHT = "#F8E1E8"
NEUTRAL_LIGHT = "#F3F4F6"
CELL_A = "#D7DBEA"
CELL_B = "#E8EBF4"
CELL_ORANGE = "#EFD9CF"
BG = "#F6F7FB"
TEXT = "#1F2937"
GRID = "rgba(31,41,55,0.12)"
TABLE_CONFIG = {"displayModeBar": False, "displaylogo": False, "responsive": False}
CHART_CONFIG = {"displayModeBar": True, "displaylogo": False, "responsive": True}

PERIOD_MAP = {
    "out_tw1": "Outlook Q1",
    "out_tw2": "Outlook Q2",
    "out_tw3": "Outlook Q3",
    "out_tw4": "Outlook Q4",
    "full_year": "Full Year",
}
PERIOD_ORDER = list(PERIOD_MAP.keys())
PDB_COMPONENTS = [
    "Konsumsi RT",
    "Konsumsi LNPRT",
    "PKP",
    "PMTB",
    "Change in Stocks",
    "Ekspor",
    "Impor",
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
    "simulasi": "Simulasi PDB & Kesejahteraan",
    "makro": "Blok Makro",
    "pdb": "Accounting / PDB",
    "moneter": "Blok Moneter",
    "fiskal": "Blok Fiskal",
}
BLOCK_NOTES = {
    "simulasi": "Tabel utama mengambil indikator dari Blok Accounting nominal 2026.",
    "makro": "Indikator Makroekonomi.",
    "pdb": "Outlook Baseline PDB 2026.",
    "moneter": "Variabel Moneter.",
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
        .block-title {{ font-size: 1.05rem; font-weight: 700; color: {TEXT}; margin: 0.15rem 0 0.4rem 0; }}
        .sub-title {{ font-size: 0.95rem; font-weight: 700; color: {TEXT}; margin: 0.35rem 0 0.35rem 0; }}
        .section-card {{ border: 1px solid rgba(62,109,181,0.14); border-radius: 14px; padding: 0.7rem 0.8rem 0.6rem 0.8rem; background: white; box-shadow: 0 2px 10px rgba(0,0,0,0.03); margin-bottom: 0.9rem; overflow: visible; }}
        .section-note {{ color: #6B7280; font-size: 0.88rem; margin-bottom: 0.35rem; }}
        .chart-note {{ color: #6B7280; font-size: 0.84rem; margin-top: -0.1rem; margin-bottom: 0.4rem; }}
        .status-box {{ border: 1px dashed rgba(62,109,181,0.30); border-radius: 12px; padding: 0.55rem 0.75rem; background: rgba(62,109,181,0.03); color: #374151; margin-bottom: 0.75rem; font-size: 0.86rem; }}
        .fiscal-editor-header {{ display: block; margin-top: 0.35rem; margin-bottom: 0.30rem; }}
        .fiscal-editor-title {{ color: {PRIMARY}; font-size: 1.02rem; font-weight: 700; line-height: 1.2; display: inline; }}
        .fiscal-editor-unit {{ color: #111827; font-size: 0.92rem; line-height: 1.2; display: inline; margin-left: 0.35rem; }}
        div[data-testid="stDataEditor"] * {{ font-size: 0.95rem !important; }}
        .section-card {{ overflow: visible; }}
        .sticky-table-wrap {{ width: 100%; max-width: 100%; overflow: visible; overflow-y: visible; margin: 0.25rem 0 0.70rem 0; border-radius: 12px; --first-col-min: 260px; --first-col-max: 360px; --num-col-min: 92px; }}
        .sticky-table {{ border-collapse: separate; border-spacing: 0; width: max-content; min-width: 100%; font-size: 0.95rem; table-layout: fixed; }}
        .sticky-table thead th {{ position: sticky; top: 0; z-index: 4; color: white; font-weight: 700; white-space: nowrap; box-shadow: inset 0 -1px 0 rgba(255,255,255,0.18); }}
        .sticky-table th, .sticky-table td {{ padding: 8px 10px; border-right: 1px solid rgba(255,255,255,0.42); border-bottom: 1px solid rgba(255,255,255,0.42); vertical-align: middle; }}
        .sticky-table th:first-child, .sticky-table td:first-child {{ position: sticky; left: 0; min-width: var(--first-col-min); max-width: var(--first-col-max); width: var(--first-col-min); white-space: normal; word-break: break-word; }}
        .sticky-table thead th:first-child {{ z-index: 6; }}
        .sticky-table tbody td:first-child {{ z-index: 3; }}
        .sticky-table .num {{ text-align: center; white-space: nowrap; min-width: var(--num-col-min); }}
        .sticky-table .txt {{ text-align: left; }}
        .sticky-table-wrap::-webkit-scrollbar {{ height: 10px; }}
        .sticky-table-wrap::-webkit-scrollbar-thumb {{ background: rgba(62,109,181,0.25); border-radius: 999px; }}
        .sticky-table-wrap::-webkit-scrollbar-track {{ background: rgba(62,109,181,0.07); border-radius: 999px; }}
        .fiscal-editor-header {{ display: block; margin-top: 0.35rem; margin-bottom: 0.30rem; }}
        .fiscal-editor-title {{ color: {PRIMARY}; font-size: 1.02rem; font-weight: 700; line-height: 1.2; display: inline; }}
        .fiscal-editor-unit {{ color: #111827; font-size: 0.92rem; line-height: 1.2; display: inline; margin-left: 0.35rem; }}
        .simfiskal-editor-wrap {{ width: fit-content; max-width: 100%; overflow: visible; margin-bottom: 0.55rem; }}
        .simfiskal-editor-wrap div[data-testid="stDataEditor"] {{ width: fit-content !important; min-width: 760px; }}
        .simfiskal-editor-wrap div[data-testid="stDataEditor"] [data-testid="stDataFrameResizable"] {{ width: fit-content !important; }}
        .simfiskal-editor-wrap div[data-testid="stDataEditor"] table {{ width: auto !important; }}
        .simfiskal-editor-wrap div[data-testid="stDataEditor"] th,
        .simfiskal-editor-wrap div[data-testid="stDataEditor"] td {{ white-space: nowrap; }}
        .simfiskal-editor-wrap div[data-testid="stDataEditor"] th:first-child,
        .simfiskal-editor-wrap div[data-testid="stDataEditor"] td:first-child {{ min-width: 250px; }}
    </style>
    """,
    unsafe_allow_html=True,
)


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    mapper = {}
    for c in df.columns:
        key = str(c).strip().lower().replace(" ", "_").replace(".", "").replace("-", "_")
        mapper[c] = key
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
    rows = []
    numeric_cols = [c for c in work.columns if c != "indikator"]
    for ind in expected_rows:
        found = work.loc[work["indikator"] == ind]
        if not found.empty:
            rows.append(found.iloc[0].to_dict())
        else:
            row = {"indikator": ind}
            for c in numeric_cols:
                row[c] = None
            rows.append(row)
    return pd.DataFrame(rows)


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
        return str(local_path), f"Sumber data otomatis: {REPO_FILE_NAME}"
    if GITHUB_RAW_XLSX_URL:
        return load_excel_bytes_from_url(GITHUB_RAW_XLSX_URL), "Sumber data otomatis: GitHub Raw URL dari st.secrets['github_raw_xlsx_url']"
    return None, "File Excel belum ditemukan. Simpan dashboard PDB.xlsx di root repo yang sama dengan app.py, atau isi st.secrets['github_raw_xlsx_url'] dengan raw URL GitHub file tersebut."


def _format_id_number(val: float, decimals: int = 0) -> str:
    s = f"{float(val):,.{decimals}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_id0(val):
    if pd.isna(val) or val is None:
        return "—"
    try:
        return _format_id_number(val, decimals=0)
    except Exception:
        return str(val)


def fmt_pct_id2(val):
    if pd.isna(val) or val is None:
        return "—"
    try:
        return _format_id_number(val, decimals=2) + "%"
    except Exception:
        return str(val)


def make_tick_values(series: pd.Series, n: int = 6):
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty:
        return [], []
    vmin = float(s.min())
    vmax = float(s.max())
    if math.isclose(vmin, vmax):
        vals = [0] if math.isclose(vmin, 0.0) else [vmin - abs(vmin)*0.1, vmin, vmin + abs(vmin)*0.1]
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
    needed = ["out_tw1", "out_tw2", "out_tw3", "out_tw4"]
    for col in needed:
        if col not in work.columns:
            work[col] = None
        work[col] = pd.to_numeric(work[col], errors="coerce")
    work["full_year"] = work[needed].sum(axis=1, min_count=1)
    return work


def get_table_block_spec(block_key: str = "", growth_mode: bool = False) -> dict:
    block_key = (block_key or "").lower().strip()
    if growth_mode:
        return {"first_min": 300, "first_max": 400, "num_min": 96, "wrap": 20}
    specs = {
        "pdb": {"first_min": 300, "first_max": 400, "num_min": 96, "wrap": 20},
        "moneter": {"first_min": 250, "first_max": 340, "num_min": 92, "wrap": 18},
        "fiskal": {"first_min": 240, "first_max": 330, "num_min": 92, "wrap": 18},
        "makro": {"first_min": 240, "first_max": 330, "num_min": 92, "wrap": 18},
        "simulasi": {"first_min": 260, "first_max": 340, "num_min": 92, "wrap": 18},
    }
    return specs.get(block_key, {"first_min": 250, "first_max": 340, "num_min": 92, "wrap": 18})


def wrap_table_label(text: object, width: int = 18) -> str:
    if text is None or pd.isna(text):
        return "—"
    s = str(text).strip()
    if not s or s == "nan":
        return "—"
    if len(s) <= width:
        return s
    return "<br>".join(textwrap.wrap(s, width=width, break_long_words=False, break_on_hyphens=False))


def html_escape_keep_breaks(text: object) -> str:
    if text is None:
        s = "—"
    else:
        try:
            s = "—" if pd.isna(text) else str(text)
        except Exception:
            s = str(text)
    return html.escape(s).replace("&lt;br&gt;", "<br>")


def format_display_sticky(df: pd.DataFrame, value_formatter=fmt_id0, wrap_width: int = 18) -> pd.DataFrame:
    view = df.copy()
    ordered_cols = ["indikator", *PERIOD_ORDER]
    for c in ordered_cols:
        if c not in view.columns:
            view[c] = None
    view = view[ordered_cols].rename(columns={"indikator": "Indikator", **PERIOD_MAP})
    view["Indikator"] = view["Indikator"].apply(lambda x: wrap_table_label(x, width=wrap_width))
    for c in view.columns[1:]:
        view[c] = view[c].apply(value_formatter)
    return view.fillna("—")


def build_sticky_html_table(
    df: pd.DataFrame,
    header_fill: str,
    row_fill_1: str,
    row_fill_2: str,
    value_formatter=fmt_id0,
    raw_value_df: Optional[pd.DataFrame] = None,
    growth_mode: bool = False,
    block_key: str = "",
) -> str:
    spec = get_table_block_spec(block_key=block_key, growth_mode=growth_mode)
    view = format_display_sticky(df, value_formatter=value_formatter, wrap_width=spec["wrap"])
    cols = list(view.columns)
    rows_html = []
    raw_ordered = None
    if growth_mode and raw_value_df is not None:
        raw_ordered = raw_value_df[["indikator", *PERIOD_ORDER]].copy()

    for i in range(len(view)):
        row_bg = row_fill_1 if i % 2 == 0 else row_fill_2
        cells = []
        first_val = html_escape_keep_breaks(view.iloc[i, 0])
        cells.append(f'<td class="txt" style="background:{row_bg}; left:0;">{first_val}</td>')
        for j in range(1, len(cols)):
            cell_bg = row_bg
            if growth_mode and raw_ordered is not None:
                raw_col = PERIOD_ORDER[j - 1]
                cell_bg = growth_color(raw_ordered.iloc[i][raw_col])
            val = html_escape_keep_breaks(view.iloc[i, j])
            cells.append(f'<td class="num" style="background:{cell_bg};">{val}</td>')
        rows_html.append('<tr>' + ''.join(cells) + '</tr>')

    header_cells = []
    for idx, c in enumerate(cols):
        cls = 'txt' if idx == 0 else 'num'
        extra = 'left:0;' if idx == 0 else ''
        header_cells.append(f'<th class="{cls}" style="background:{header_fill}; {extra}">{html.escape(str(c))}</th>')

    wrapper_style = (
        f'--first-col-min:{spec["first_min"]}px; '
        f'--first-col-max:{spec["first_max"]}px; '
        f'--num-col-min:{spec["num_min"]}px;'
    )
    return (
        f'<div class="sticky-table-wrap" style="{wrapper_style}">'
        '<table class="sticky-table">'
        '<thead><tr>' + ''.join(header_cells) + '</tr></thead>'
        '<tbody>' + ''.join(rows_html) + '</tbody>'
        '</table>'
        '</div>'
    )


def growth_color(value):
    if pd.isna(value) or value is None:
        return NEUTRAL_LIGHT
    try:
        v = float(value)
    except Exception:
        return NEUTRAL_LIGHT
    if v > 0:
        return POS_LIGHT
    if v < 0:
        return NEG_LIGHT
    return NEUTRAL_LIGHT


def _choose_realisasi_column(columns: list[str], target: str) -> Optional[str]:
    target_norm = target.lower().strip().replace(" ", "_").replace(".", "").replace("-", "_")
    for col in columns:
        c = str(col).lower().strip().replace(" ", "_").replace(".", "").replace("-", "_")
        if c == target_norm:
            return col
    return None


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
        fy = row_2026[source_col].sum() if not row_2026.empty else None
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

    mapping = {}
    alias_map = {
        "Konsumsi RT": ["Konsumsi_RT"],
        "Konsumsi LNPRT": ["Konsumsi_LNPRT"],
        "PKP": ["PKP"],
        "PMTB": ["PMTB"],
        "Change in Stocks": ["Change_in_Stocks"],
        "Ekspor": ["Ekspor"],
        "Impor": ["Impor"],
    }
    for indikator in PDB_AGGREGATE_INPUTS:
        source_col = _choose_realisasi_column(list(raw.columns), indikator)
        if source_col is None:
            for alias in alias_map.get(indikator, []):
                source_col = _choose_realisasi_column(list(raw.columns), alias)
                if source_col is not None:
                    break
        if source_col is not None:
            mapping[indikator] = source_col

    level_df = raw[["tanggal", *mapping.values()]].copy().rename(columns={v: k for k, v in mapping.items()})
    for indikator in PDB_AGGREGATE_INPUTS:
        if indikator not in level_df.columns:
            level_df[indikator] = None
        level_df[indikator] = pd.to_numeric(level_df[indikator], errors="coerce")
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
    yoy_table = coerce_schema(_build_growth_table(level_df, periods=4, growth_name="yoy"), "pdb")
    qtq_table = coerce_schema(_build_growth_table(level_df, periods=1, growth_name="qtq"), "pdb")
    hist_long = level_df.melt(id_vars="tanggal", value_vars=PDB_COMPONENTS, var_name="komponen", value_name="nilai")
    hist_long["nilai_fmt"] = hist_long["nilai"].apply(fmt_id0)
    growth_long_parts = []
    for indikator in PDB_COMPONENTS:
        temp = level_df[["tanggal", indikator]].copy().sort_values("tanggal")
        temp["komponen"] = indikator
        temp["yoy"] = temp[indikator].pct_change(4) * 100
        temp["qtq"] = temp[indikator].pct_change(1) * 100
        growth_long_parts.append(temp[["tanggal", "komponen", "yoy", "qtq"]])
    growth_long = pd.concat(growth_long_parts, ignore_index=True)
    return nominal_table, {"level": hist_long, "growth": growth_long}, {"nominal": nominal_table, "yoy": yoy_table, "qtq": qtq_table}, level_df


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
            data["pdb"] = coerce_schema(df, "pdb")
        return data, pdb_history, pdb_tables, source_status
    except Exception as e:
        return data, pdb_history, pdb_tables, f"Gagal membaca sumber Excel otomatis: {e}"


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


def compute_column_widths(view: pd.DataFrame, min_px: int = 82, max_px: int = 320) -> list[int]:
    widths = []
    for idx, col in enumerate(view.columns):
        texts = [str(col)] + [str(v) for v in view[col].tolist()]
        max_len = max(len(t) for t in texts) if texts else len(str(col))
        if idx == 0:
            width = min(max(130, 8 * max_len + 28), max_px)
        else:
            width = min(max(min_px, 7 * max_len + 20), 150)
        widths.append(int(width))
    return widths


def make_table(df: pd.DataFrame, header_fill: str, row_fill_1: str, row_fill_2: str, height=320, value_formatter=fmt_id0):
    view = format_display(df, value_formatter=value_formatter)
    cols = list(view.columns)
    row_colors = [row_fill_1 if i % 2 == 0 else row_fill_2 for i in range(len(view))]
    fill_matrix = [[c for c in row_colors] for _ in cols]
    widths = compute_column_widths(view)
    aligns = ["left"] + ["center"] * (len(cols) - 1)
    fig = go.Figure(data=[go.Table(
        columnwidth=widths,
        header=dict(values=[f"<b>{c}</b>" for c in cols], fill_color=header_fill, font=dict(color="white", size=12), align=aligns, height=34, line_color="white"),
        cells=dict(values=[view[c] for c in cols], fill_color=fill_matrix, font=dict(color=TEXT, size=12), align=aligns, height=31, line_color="white"),
    )])
    fig.update_layout(
        width=sum(widths) + 24,
        height=height,
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def make_growth_table(df: pd.DataFrame, header_fill: str, height=260, value_formatter=fmt_pct_id2):
    table_df = filter_growth_rows(df)
    view = format_display(table_df, value_formatter=value_formatter)
    cols = list(view.columns)
    raw_ordered = table_df[["indikator", *PERIOD_ORDER]].copy()
    fill_matrix = []
    indicator_colors = [NEUTRAL_LIGHT if i % 2 == 0 else "#FFFFFF" for i in range(len(view))]
    fill_matrix.append(indicator_colors)
    for col in PERIOD_ORDER:
        fill_matrix.append([growth_color(v) for v in raw_ordered[col].tolist()])
    widths = compute_column_widths(view)
    aligns = ["left"] + ["center"] * (len(cols) - 1)
    fig = go.Figure(data=[go.Table(
        columnwidth=widths,
        header=dict(values=[f"<b>{c}</b>" for c in cols], fill_color=header_fill, font=dict(color="white", size=12), align=aligns, height=34, line_color="white"),
        cells=dict(values=[view[c] for c in cols], fill_color=fill_matrix, font=dict(color=TEXT, size=12), align=aligns, height=31, line_color="white"),
    )])
    fig.update_layout(
        width=sum(widths) + 24,
        height=height,
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def placeholder_chart(msg: str, height: int = 380):
    fig = go.Figure()
    fig.add_annotation(text=msg, x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False, font=dict(size=14, color="#6B7280"))
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=40, b=10), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


def make_pdb_history_chart(pdb_history: Optional[dict], selected_components: list[str]):
    if not pdb_history or pdb_history.get("level") is None or pdb_history["level"].empty:
        return placeholder_chart("Data historis PDB belum tersedia pada sumber Excel otomatis.")
    plot_df = pdb_history["level"]
    plot_df = plot_df[plot_df["komponen"].isin(selected_components)].copy()
    if plot_df.empty:
        return placeholder_chart("Komponen historis yang dipilih belum memiliki data.")
    fig = px.line(plot_df, x="tanggal", y="nilai", color="komponen", color_discrete_sequence=[PRIMARY, ACCENT, SUCCESS, PURPLE, NEGATIVE, "#F4A261", "#4C78A8", "#6C8EAD"], custom_data=["nilai_fmt"])
    fig.update_traces(mode="lines+markers", line=dict(width=2.6), marker=dict(size=5.5), hovertemplate="<b>%{fullData.name}</b><br>%{x|%Y-%m-%d}: %{customdata[0]}<extra></extra>")
    tickvals, ticktext = make_tick_values(plot_df["nilai"])
    fig.update_layout(title="Historis Komponen PDB", height=395, margin=dict(l=10, r=10, t=50, b=10), hovermode="x unified", legend_title_text="Komponen", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=True, gridcolor=GRID, zeroline=False, tickmode="array", tickvals=tickvals, ticktext=ticktext)
    return fig


def make_growth_chart(pdb_history: Optional[dict], selected_components: list[str], growth_col: str, title: str, colors=None):
    if not pdb_history or pdb_history.get("growth") is None or pdb_history["growth"].empty:
        return placeholder_chart("Data pertumbuhan PDB belum tersedia pada sumber Excel otomatis.")
    plot_df = pdb_history["growth"]
    plot_df = plot_df[plot_df["komponen"].isin(selected_components)].copy()
    if plot_df.empty:
        return placeholder_chart("Komponen pertumbuhan yang dipilih belum memiliki data.")
    plot_df["nilai_fmt"] = plot_df[growth_col].apply(fmt_pct_id2)
    fig = px.line(plot_df, x="tanggal", y=growth_col, color="komponen", color_discrete_sequence=colors or [PRIMARY, ACCENT, SUCCESS, PURPLE, NEGATIVE, "#F4A261", "#4C78A8", "#6C8EAD"], custom_data=["nilai_fmt"])
    fig.update_traces(mode="lines+markers", line=dict(width=2.4), marker=dict(size=5.0), hovertemplate="<b>%{fullData.name}</b><br>%{x|%Y-%m-%d}: %{customdata[0]}<extra></extra>")
    tickvals, ticktext = make_tick_values_pct(plot_df[growth_col])
    fig.update_layout(title=title, height=395, margin=dict(l=10, r=10, t=50, b=10), hovermode="x unified", legend_title_text="Komponen", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=True, gridcolor=GRID, zeroline=True, tickmode="array", tickvals=tickvals, ticktext=ticktext)
    return fig


def block_card(title: str, note: Optional[str] = None):
    st.markdown(f'<div class="block-title">{title}</div>', unsafe_allow_html=True)
    if note:
        st.markdown(f'<div class="section-note">{note}</div>', unsafe_allow_html=True)


def sub_title(text: str):
    st.markdown(f'<div class="sub-title">{text}</div>', unsafe_allow_html=True)




def render_table_block(block_df: pd.DataFrame, accent: bool = False, block_key: str = "", chart_key: Optional[str] = None):
    html_table = build_sticky_html_table(
        block_df,
        header_fill=PRIMARY,
        row_fill_1=CELL_A if not accent else CELL_ORANGE,
        row_fill_2=CELL_B if not accent else "#F4E5DE",
        value_formatter=fmt_id0,
        raw_value_df=None,
        growth_mode=False,
        block_key=block_key,
    )
    st.markdown(html_table, unsafe_allow_html=True)



def render_growth_table(df: pd.DataFrame, title: str, header_fill: str, chart_key: Optional[str] = None):
    sub_title(title)
    table_df = filter_growth_rows(df)
    html_table = build_sticky_html_table(
        table_df,
        header_fill=header_fill,
        row_fill_1=NEUTRAL_LIGHT,
        row_fill_2="#FFFFFF",
        value_formatter=fmt_pct_id2,
        raw_value_df=table_df,
        growth_mode=True,
        block_key="pdb",
    )
    st.markdown(html_table, unsafe_allow_html=True)

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
    st.markdown('<div class="simfiskal-editor-wrap">', unsafe_allow_html=True)
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
    st.markdown('</div>', unsafe_allow_html=True)
    edited_df = edited_df[["indikator", *SIMULASI_FISKAL_COLS]].copy()
    edited_df["indikator"] = SIMULASI_FISKAL_ROWS
    for col in SIMULASI_FISKAL_COLS:
        edited_df[col] = pd.to_numeric(edited_df[col], errors="coerce").fillna(0.0)
    st.session_state["simulasi_fiskal_df"] = edited_df
    return edited_df



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
render_table_block(filter_main_pdb_rows(ensure_full_year_from_quarters(workbook["pdb"])), block_key="pdb", chart_key="main_pdb_nominal_2026")
simulasi_fiskal_df = render_simulasi_fiskal_editor()

tab_makro, tab_pdb, tab_moneter, tab_fiskal = st.tabs(["Blok Makro", "Blok Accounting", "Blok Moneter", "Blok Fiskal"])

with tab_makro:
    block_card(BLOCK_TITLES["makro"], BLOCK_NOTES["makro"])
    render_table_block(workbook["makro"], block_key="makro", chart_key="tab_makro_table")

with tab_pdb:
    block_card(BLOCK_TITLES["pdb"], BLOCK_NOTES["pdb"])
    sub_title("Tabel Nominal 2026")
    render_table_block(workbook["pdb"], block_key="pdb", chart_key="tab_pdb_nominal_2026")
    if pdb_tables is not None:
        render_growth_table(pdb_tables.get("yoy", empty_df("pdb")), "Tabel Year on Year (YoY)", header_fill=PRIMARY, chart_key="tab_pdb_yoy_table")
        render_growth_table(pdb_tables.get("qtq", empty_df("pdb")), "Tabel Quarter to Quarter (QtQ)", header_fill=PRIMARY, chart_key="tab_pdb_qtq_table")
    st.markdown("<div class='chart-note'></div>", unsafe_allow_html=True)
    selected_components = st.multiselect("Pilih komponen historis yang ingin ditampilkan", options=PDB_COMPONENTS, default=PDB_COMPONENTS, key="hist_components_pdb")
    selected_components = selected_components or PDB_COMPONENTS
    selected_growth_components = filter_growth_components(selected_components)
    ch1, ch2, ch3 = st.tabs(["Historis Level", "Year on Year (YoY)", "Quarter to Quarter (QtQ)"])
    with ch1:
        st.plotly_chart(make_pdb_history_chart(pdb_history, selected_components), use_container_width=True, config=CHART_CONFIG, key="tab_pdb_hist_level_chart")
    with ch2:
        st.plotly_chart(make_growth_chart(pdb_history, selected_growth_components, "yoy", "Pertumbuhan Year on Year (YoY)", colors=[SUCCESS, ACCENT, PRIMARY, PURPLE, NEGATIVE, "#F4A261", "#4C78A8", "#6C8EAD"]), use_container_width=True, config=CHART_CONFIG, key="tab_pdb_hist_yoy_chart")
    with ch3:
        st.plotly_chart(make_growth_chart(pdb_history, selected_growth_components, "qtq", "Pertumbuhan Quarter to Quarter (QtQ)", colors=[PURPLE, SUCCESS, PRIMARY, ACCENT, NEGATIVE, "#F4A261", "#4C78A8", "#6C8EAD"]), use_container_width=True, config=CHART_CONFIG, key="tab_pdb_hist_qtq_chart")

with tab_moneter:
    block_card(BLOCK_TITLES["moneter"], BLOCK_NOTES["moneter"])
    render_table_block(workbook["moneter"], block_key="moneter", chart_key="tab_moneter_table")

with tab_fiskal:
    block_card(BLOCK_TITLES["fiskal"], BLOCK_NOTES["fiskal"])
    render_table_block(workbook["fiskal"], block_key="fiskal", chart_key="tab_fiskal_table")

with st.expander("Lihat struktur sumber Excel"):
    info = pd.DataFrame({
        "Sumber": [REPO_FILE_NAME, "st.secrets['github_raw_xlsx_url'] (opsional)"],
        "Keterangan": [
            "File diletakkan di repo yang sama dengan app.py sehingga otomatis terbaca saat deploy Streamlit dari GitHub.",
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
