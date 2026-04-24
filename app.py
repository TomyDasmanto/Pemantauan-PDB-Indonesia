
from io import BytesIO
from pathlib import Path
from typing import Optional, Tuple, Union
from urllib.request import urlopen

import pandas as pd
import plotly.express as px
import streamlit as st

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
SUCCESS = "#2A9D8F"
ACCENT = "#E07B39"
PURPLE = "#8A5CF6"
NEGATIVE = "#D14D72"
GRID = "rgba(31,41,55,0.12)"

PERIOD_MAP = {
    "out_tw1": "Q1",
    "out_tw2": "Q2",
    "out_tw3": "Q3",
    "out_tw4": "Q4",
    "full_year": "Full Year",
}
PERIOD_ORDER = list(PERIOD_MAP.keys())

SIMULASI_FISKAL_ROWS = [
    "Bantuan Pangan",
    "Bantuan Langsung Tunai",
    "Kenaikan Gaji",
    "Pembayaran Gaji 14",
    "Diskon Transportasi",
    "Investasi",
]
SIMULASI_FISKAL_COLS = ["out_tw1", "out_tw2", "out_tw3", "out_tw4"]

SIMULASI_MAKRO_DEFAULTS = [
    ("Pertumbuhan ekonomi (%)", 5.4),
    ("Inflasi (%)", 2.5),
    ("Tingkat bunga SUN 10 tahun", 6.9),
    ("Nilai tukar (Rp100/US$1)", 16500.0),
    ("Harga minyak (US$/barel)", 70.0),
    ("Lifting minyak (ribu barel per hari)", 610.0),
    ("Lifting Gas Bumi (ribu barel setara minyak per hari)", 984.0),
]

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
PDB_MAIN_ROWS = ["Konsumsi RT", "PKP", "PMTB", "Ekspor", "Impor", "PDB Aggregate"]
EXCLUDE_GROWTH_ROWS = ["Change in Stocks"]

DEFAULT_ROWS = {
    "makro": ["Inflasi", "Rupiah", "Yield SBN", "ICP", "Nikel", "Coal", "CPO", "Lifting"],
    "moneter": ["PUAB", "Kredit", "DPK", "M0", "OMO"],
    "fiskal": ["Pendapatan", "Belanja", "Pembiayaan", "Defisit"],
    "pdb": PDB_COMPONENTS,
}

# Aturan simulasi makro untuk Blok Fiskal.
# Setiap perubahan 0,1 dari nilai APBN 2026 menghasilkan perubahan dampak sesuai koefisien di bawah.
# revenue -> memengaruhi Penerimaan Perpajakan
# spending -> memengaruhi Belanja Pemerintah Pusat
MACRO_FISKAL_RULES = {
    "Pertumbuhan ekonomi (%)": {"target": "revenue", "coef_per_0_1": 2080.30},
    "Inflasi (%)": {"target": "revenue", "coef_per_0_1": 1862.99},
    "Tingkat bunga SUN 10 tahun": {"target": "spending", "coef_per_0_1": 1899.98},
}


def normalize_col_name(name: object) -> str:
    return str(name).strip().lower().replace(" ", "_").replace(".", "").replace("-", "_")


def fmt_id0(val):
    if pd.isna(val) or val is None:
        return "—"
    try:
        s = f"{float(val):,.0f}"
        return s.replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return str(val)


def fmt_pct(val):
    if pd.isna(val) or val is None:
        return "—"
    try:
        s = f"{float(val):,.2f}"
        return s.replace(",", "X").replace(".", ",").replace("X", ".") + "%"
    except Exception:
        return str(val)


def fmt_dec1(val):
    if pd.isna(val) or val is None:
        return "—"
    try:
        s = f"{float(val):,.1f}"
        return s.replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return str(val)


def fmt_fiskal_number(val, decimals: int = 2):
    if val is None or pd.isna(val):
        return ""
    try:
        num = float(val)
        fmt = f"{{:,.{decimals}f}}"
        if num < 0:
            return f"({fmt.format(abs(num))})".replace(",", "X").replace(".", ",").replace("X", ".")
        return fmt.format(num).replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return str(val)


def empty_df(block: str) -> pd.DataFrame:
    rows = DEFAULT_ROWS.get(block, [])
    payload = {"indikator": rows}
    for c in PERIOD_ORDER:
        payload[c] = [None] * len(rows)
    return pd.DataFrame(payload)


def ensure_schema(df: pd.DataFrame, block: str) -> pd.DataFrame:
    if df is None or df.empty:
        return empty_df(block)
    work = df.copy()
    work.columns = [normalize_col_name(c) for c in work.columns]
    if "indikator" not in work.columns and len(work.columns) > 0:
        work = work.rename(columns={work.columns[0]: "indikator"})
    for col in ["indikator", *PERIOD_ORDER]:
        if col not in work.columns:
            work[col] = None
    work = work[["indikator", *PERIOD_ORDER]].copy()
    work["indikator"] = work["indikator"].astype(str).str.strip()
    if block in DEFAULT_ROWS:
        wanted = DEFAULT_ROWS[block]
        rows = []
        for ind in wanted:
            found = work.loc[work["indikator"] == ind]
            if not found.empty:
                rows.append(found.iloc[0].to_dict())
            else:
                rows.append({"indikator": ind, **{c: None for c in PERIOD_ORDER}})
        work = pd.DataFrame(rows)
    for c in PERIOD_ORDER:
        work[c] = pd.to_numeric(work[c], errors="coerce")
    return work


def ensure_full_year_from_quarters(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return empty_df("pdb")
    work = df.copy()
    for c in SIMULASI_FISKAL_COLS:
        if c not in work.columns:
            work[c] = None
        work[c] = pd.to_numeric(work[c], errors="coerce")
    work["full_year"] = work[SIMULASI_FISKAL_COLS].sum(axis=1, min_count=1)
    return work


def load_excel_bytes_from_url(url: str) -> bytes:
    with urlopen(url) as resp:
        return resp.read()


def open_excel_source(source: Union[str, bytes, bytearray]):
    if isinstance(source, (bytes, bytearray)):
        return pd.ExcelFile(BytesIO(source), engine="openpyxl")
    return pd.ExcelFile(source, engine="openpyxl")


def detect_excel_source() -> Tuple[Optional[Union[str, bytes]], str]:
    local_path = Path(__file__).resolve().parent / REPO_FILE_NAME
    if local_path.exists():
        return str(local_path), f"Sumber data otomatis: {local_path.name} di folder repo"
    if GITHUB_RAW_XLSX_URL:
        return load_excel_bytes_from_url(GITHUB_RAW_XLSX_URL), (
            "Sumber data otomatis: GitHub Raw URL dari st.secrets['github_raw_xlsx_url']"
        )
    return None, (
        "File Excel belum ditemukan. Simpan dashboard PDB.xlsx di root repo yang sama dengan app.py, "
        "atau isi st.secrets['github_raw_xlsx_url']."
    )


def _pick_col(columns, candidate: str):
    target = normalize_col_name(candidate)
    for c in columns:
        if normalize_col_name(c) == target:
            return c
    return None


def _build_period_table_from_realisasi(raw: pd.DataFrame, year: int = 2026) -> pd.DataFrame:
    row_map = {
        "Konsumsi RT": _pick_col(raw.columns, "Konsumsi RT"),
        "Konsumsi LNPRT": _pick_col(raw.columns, "Konsumsi LNPRT"),
        "PKP": _pick_col(raw.columns, "PKP"),
        "PMTB": _pick_col(raw.columns, "PMTB"),
        "Ekspor": _pick_col(raw.columns, "Ekspor"),
        "Impor": _pick_col(raw.columns, "Impor"),
        "Change in Stocks": _pick_col(raw.columns, "Change in Stocks"),
        "Statistical Discrepancy": _pick_col(raw.columns, "Statistical Discrepancy"),
    }
    work = raw.copy().sort_values("tanggal")
    work["tahun"] = work["tanggal"].dt.year
    work["quarter"] = work["tanggal"].dt.quarter

    rows = []
    for indikator, src in row_map.items():
        if src is None:
            continue
        sy = work.loc[work["tahun"] == year, ["quarter", src]].copy()
        quarter_values = {}
        for q in [1, 2, 3, 4]:
            sel = sy.loc[sy["quarter"] == q, src]
            quarter_values[f"out_tw{q}"] = float(sel.iloc[-1]) if not sel.empty else None
        fy = sy[src].sum() if not sy.empty else None
        rows.append({"indikator": indikator, **quarter_values, "full_year": fy})

    out = pd.DataFrame(rows)
    if out.empty:
        return empty_df("pdb")

    idx = out.set_index("indikator")
    agg_vals = {}
    for c in PERIOD_ORDER:
        def gv(name):
            try:
                return pd.to_numeric(idx.loc[name, c], errors="coerce")
            except Exception:
                return 0.0
        agg_vals[c] = (
            (0 if pd.isna(gv("Konsumsi RT")) else float(gv("Konsumsi RT")))
            + (0 if pd.isna(gv("Konsumsi LNPRT")) else float(gv("Konsumsi LNPRT")))
            + (0 if pd.isna(gv("PKP")) else float(gv("PKP")))
            + (0 if pd.isna(gv("PMTB")) else float(gv("PMTB")))
            + (0 if pd.isna(gv("Change in Stocks")) else float(gv("Change in Stocks")))
            + (0 if pd.isna(gv("Ekspor")) else float(gv("Ekspor")))
            - (0 if pd.isna(gv("Impor")) else float(gv("Impor")))
            + (0 if pd.isna(gv("Statistical Discrepancy")) else float(gv("Statistical Discrepancy")))
        )

    out = pd.concat(
        [
            out[out["indikator"] != "Statistical Discrepancy"],
            pd.DataFrame([{"indikator": "PDB Aggregate", **agg_vals}]),
        ],
        ignore_index=True,
    )
    return ensure_schema(out, "pdb")


def _build_level_history(raw: pd.DataFrame) -> pd.DataFrame:
    work = raw.copy().sort_values("tanggal")
    col_rt = _pick_col(work.columns, "Konsumsi RT")
    col_lnprt = _pick_col(work.columns, "Konsumsi LNPRT")
    col_pkp = _pick_col(work.columns, "PKP")
    col_pmtb = _pick_col(work.columns, "PMTB")
    col_exp = _pick_col(work.columns, "Ekspor")
    col_imp = _pick_col(work.columns, "Impor")
    col_stocks = _pick_col(work.columns, "Change in Stocks")
    col_disc = _pick_col(work.columns, "Statistical Discrepancy")

    wide = pd.DataFrame({
        "tanggal": work["tanggal"],
        "Konsumsi RT": pd.to_numeric(work[col_rt], errors="coerce") if col_rt else None,
        "Konsumsi LNPRT": pd.to_numeric(work[col_lnprt], errors="coerce") if col_lnprt else None,
        "PKP": pd.to_numeric(work[col_pkp], errors="coerce") if col_pkp else None,
        "PMTB": pd.to_numeric(work[col_pmtb], errors="coerce") if col_pmtb else None,
        "Change in Stocks": pd.to_numeric(work[col_stocks], errors="coerce") if col_stocks else None,
        "Ekspor": pd.to_numeric(work[col_exp], errors="coerce") if col_exp else None,
        "Impor": pd.to_numeric(work[col_imp], errors="coerce") if col_imp else None,
    })
    discrepancy = pd.to_numeric(work[col_disc], errors="coerce") if col_disc else 0.0
    wide["PDB Aggregate"] = (
        wide["Konsumsi RT"].fillna(0)
        + wide["Konsumsi LNPRT"].fillna(0)
        + wide["PKP"].fillna(0)
        + wide["PMTB"].fillna(0)
        + wide["Change in Stocks"].fillna(0)
        + wide["Ekspor"].fillna(0)
        - wide["Impor"].fillna(0)
        + pd.to_numeric(discrepancy, errors="coerce").fillna(0)
    )
    return wide


def _build_growth_tables_from_wide(wide: pd.DataFrame):
    long_rows = []
    growth_rows = []
    yoy_rows = []
    qtq_rows = []
    date_map = {1: "out_tw1", 2: "out_tw2", 3: "out_tw3", 4: "out_tw4"}

    for comp in PDB_COMPONENTS:
        s = wide[["tanggal", comp]].copy().sort_values("tanggal")
        s["nilai"] = pd.to_numeric(s[comp], errors="coerce")
        s["komponen"] = comp
        s["nilai_fmt"] = s["nilai"].apply(fmt_id0)
        s["yoy"] = s["nilai"].pct_change(4) * 100
        s["qtq"] = s["nilai"].pct_change(1) * 100
        long_rows.append(s[["tanggal", "komponen", "nilai", "nilai_fmt"]])
        growth_rows.append(s[["tanggal", "komponen", "yoy", "qtq"]])

        s["tahun"] = s["tanggal"].dt.year
        s["quarter"] = s["tanggal"].dt.quarter
        s26 = s[s["tahun"] == 2026]
        yoy_row = {"indikator": comp}
        qtq_row = {"indikator": comp}
        for q in [1, 2, 3, 4]:
            sel = s26[s26["quarter"] == q]
            yoy_row[date_map[q]] = float(sel["yoy"].iloc[-1]) if (not sel.empty and pd.notna(sel["yoy"].iloc[-1])) else None
            qtq_row[date_map[q]] = float(sel["qtq"].iloc[-1]) if (not sel.empty and pd.notna(sel["qtq"].iloc[-1])) else None
        annual = s.groupby("tahun", as_index=False)["nilai"].sum()
        annual["yoy"] = annual["nilai"].pct_change(1) * 100
        annual26 = annual.loc[annual["tahun"] == 2026, "yoy"]
        yoy_row["full_year"] = float(annual26.iloc[-1]) if (not annual26.empty and pd.notna(annual26.iloc[-1])) else None
        qtq_non_null = s["qtq"].dropna()
        qtq_row["full_year"] = float(qtq_non_null.iloc[-1]) if not qtq_non_null.empty else None
        yoy_rows.append(yoy_row)
        qtq_rows.append(qtq_row)

    return (
        pd.concat(long_rows, ignore_index=True),
        pd.concat(growth_rows, ignore_index=True),
        ensure_schema(pd.DataFrame(yoy_rows), "pdb"),
        ensure_schema(pd.DataFrame(qtq_rows), "pdb"),
    )


def derive_pdb_from_realisasi(source: Union[str, bytes]):
    xls = open_excel_source(source)
    sheet_map = {s.lower().strip(): s for s in xls.sheet_names}
    if "realisasi" not in sheet_map:
        return empty_df("pdb"), None, None
    raw = pd.read_excel(xls, sheet_name=sheet_map["realisasi"], engine="openpyxl")
    raw = raw.rename(columns={raw.columns[0]: "tanggal"}).copy()
    raw["tanggal"] = pd.to_datetime(raw["tanggal"], errors="coerce")
    raw = raw.dropna(subset=["tanggal"]).sort_values("tanggal").reset_index(drop=True)
    pdb_df = _build_period_table_from_realisasi(raw)
    wide = _build_level_history(raw)
    level_long, growth_long, yoy_df, qtq_df = _build_growth_tables_from_wide(wide)
    return pdb_df, {"level": level_long, "growth": growth_long, "wide": wide}, {"yoy": yoy_df, "qtq": qtq_df}


def load_dashboard_data():
    data = {k: empty_df(k) for k in ["makro", "moneter", "fiskal", "pdb"]}
    pdb_history = None
    pdb_tables = None
    source, status = detect_excel_source()
    if source is None:
        return data, pdb_history, pdb_tables, status
    try:
        xls = open_excel_source(source)
        lower_sheet_map = {s.lower().strip(): s for s in xls.sheet_names}
        for block in ["makro", "moneter", "fiskal"]:
            if block in lower_sheet_map:
                data[block] = ensure_schema(
                    pd.read_excel(xls, sheet_name=lower_sheet_map[block], engine="openpyxl"),
                    block,
                )
        if "realisasi" in lower_sheet_map:
            data["pdb"], pdb_history, pdb_tables = derive_pdb_from_realisasi(source)
        elif "pdb" in lower_sheet_map:
            data["pdb"] = ensure_schema(
                pd.read_excel(xls, sheet_name=lower_sheet_map["pdb"], engine="openpyxl"),
                "pdb",
            )
        return data, pdb_history, pdb_tables, status
    except Exception as e:
        return data, pdb_history, pdb_tables, f"Gagal membaca sumber Excel otomatis: {e}"


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
    df["indikator"] = SIMULASI_FISKAL_ROWS
    for c in SIMULASI_FISKAL_COLS:
        df[c] = pd.to_numeric(df.get(c, 0.0), errors="coerce").fillna(0.0)
    return df[["indikator", *SIMULASI_FISKAL_COLS]]


def build_simulasi_makro_df() -> pd.DataFrame:
    return pd.DataFrame({
        "indikator": [row[0] for row in SIMULASI_MAKRO_DEFAULTS],
        "apbn_2026": [row[1] for row in SIMULASI_MAKRO_DEFAULTS],
        "shock": [None] * len(SIMULASI_MAKRO_DEFAULTS),
    })


def get_simulasi_makro_df() -> pd.DataFrame:
    if "simulasi_makro_df" not in st.session_state:
        st.session_state["simulasi_makro_df"] = build_simulasi_makro_df()
    df = st.session_state["simulasi_makro_df"].copy()
    df["indikator"] = [row[0] for row in SIMULASI_MAKRO_DEFAULTS]
    df["apbn_2026"] = [row[1] for row in SIMULASI_MAKRO_DEFAULTS]
    df["shock"] = pd.to_numeric(df.get("shock"), errors="coerce")
    return df[["indikator", "apbn_2026", "shock"]]


def calculate_macro_fiskal_impacts(simulasi_makro_df: Optional[pd.DataFrame]) -> dict:
    detail = {
        "revenue": {},
        "spending": {},
        "revenue_total": 0.0,
        "spending_total": 0.0,
    }
    if simulasi_makro_df is None or simulasi_makro_df.empty:
        return detail

    work = simulasi_makro_df.copy()
    work["indikator"] = work["indikator"].astype(str).str.strip()

    for indikator, meta in MACRO_FISKAL_RULES.items():
        row = work.loc[work["indikator"] == indikator]
        impact_val = 0.0
        if not row.empty:
            apbn_val = pd.to_numeric(row.iloc[0].get("apbn_2026"), errors="coerce")
            shock_val = pd.to_numeric(row.iloc[0].get("shock"), errors="coerce")
            if pd.notna(apbn_val) and pd.notna(shock_val):
                delta = float(shock_val) - float(apbn_val)
                impact_val = round((delta / 0.1) * float(meta["coef_per_0_1"]), 2)
        target = meta["target"]
        detail[target][indikator] = impact_val
        total_key = f"{target}_total"
        detail[total_key] = round(detail[total_key] + impact_val, 2)

    return detail


def apply_simulasi_fiskal_to_pdb_nominal(pdb_df: pd.DataFrame, simulasi_df: pd.DataFrame) -> pd.DataFrame:
    if pdb_df is None or pdb_df.empty:
        return pdb_df
    work = ensure_full_year_from_quarters(pdb_df.copy())
    sim = simulasi_df.copy()
    sim["indikator"] = sim["indikator"].astype(str).str.strip()

    rules = [
        {
            "sim_indicator": "Bantuan Pangan",
            "target_indicator": "PKP",
            "divisors": {"out_tw1": 1.82, "out_tw2": 1.86, "out_tw3": 1.88, "out_tw4": 1.91},
        },
        {
            "sim_indicator": "Bantuan Langsung Tunai",
            "target_indicator": "Konsumsi RT",
            "divisors": {"out_tw1": 1.82, "out_tw2": 1.84, "out_tw3": 1.85, "out_tw4": 1.86},
        },
        {
            "sim_indicator": "Kenaikan Gaji",
            "target_indicator": "Konsumsi RT",
            "divisors": {"out_tw1": 1.82, "out_tw2": 1.84, "out_tw3": 1.85, "out_tw4": 1.86},
        },
        {
            "sim_indicator": "Pembayaran Gaji 14",
            "target_indicator": "Konsumsi RT",
            "divisors": {"out_tw1": 1.82, "out_tw2": 1.84, "out_tw3": 1.85, "out_tw4": 1.86},
        },
        {
            "sim_indicator": "Diskon Transportasi",
            "target_indicator": "Konsumsi RT",
            "divisors": {"out_tw1": 1.82, "out_tw2": 1.84, "out_tw3": 1.85, "out_tw4": 1.86},
        },
        {
            "sim_indicator": "Investasi",
            "target_indicator": "PMTB",
            "divisors": {"out_tw1": 1.66, "out_tw2": 1.66, "out_tw3": 1.67, "out_tw4": 1.67},
        },
    ]

    agg_mask = work["indikator"].astype(str).str.strip() == "PDB Aggregate"
    for rule in rules:
        sim_row = sim.loc[sim["indikator"] == rule["sim_indicator"]]
        if sim_row.empty:
            continue
        target_mask = work["indikator"].astype(str).str.strip() == rule["target_indicator"]
        if not target_mask.any():
            continue
        for col, div in rule["divisors"].items():
            input_val = pd.to_numeric(sim_row.iloc[0].get(col, 0.0), errors="coerce")
            input_val = 0.0 if pd.isna(input_val) else float(input_val)
            addition = input_val / div if div else 0.0
            work.loc[target_mask, col] = pd.to_numeric(work.loc[target_mask, col], errors="coerce").fillna(0.0) + addition
            if agg_mask.any():
                work.loc[agg_mask, col] = pd.to_numeric(work.loc[agg_mask, col], errors="coerce").fillna(0.0) + addition
    return ensure_full_year_from_quarters(work)


def build_adjusted_top_growth_tables(pdb_history: Optional[dict], adjusted_nominal: pd.DataFrame):
    if not pdb_history or pdb_history.get("wide") is None or adjusted_nominal is None or adjusted_nominal.empty:
        return {"yoy": empty_df("pdb"), "qtq": empty_df("pdb")}
    wide = pdb_history["wide"].copy()
    date_map = {
        "out_tw1": pd.Timestamp("2026-03-31"),
        "out_tw2": pd.Timestamp("2026-06-30"),
        "out_tw3": pd.Timestamp("2026-09-30"),
        "out_tw4": pd.Timestamp("2026-12-31"),
    }
    adj = adjusted_nominal.copy()
    adj["indikator"] = adj["indikator"].astype(str).str.strip()
    for _, row in adj.iterrows():
        indikator = row["indikator"]
        if indikator not in PDB_COMPONENTS:
            continue
        for col, dt in date_map.items():
            val = pd.to_numeric(row.get(col), errors="coerce")
            if pd.notna(val):
                wide.loc[wide["tanggal"] == dt, indikator] = float(val)
    _, _, yoy_df, qtq_df = _build_growth_tables_from_wide(wide)
    return {"yoy": yoy_df, "qtq": qtq_df}


def render_simulasi_fiskal_editor() -> pd.DataFrame:
    st.markdown("### Simulasi Fiskal (dalam miliar)")
    st.caption(
        "Panel simulasi fiskal berada di bawah Tabel Utama. Setelah tombol diterapkan, "
        "Tabel Utama langsung menyesuaikan pada rerun berikutnya."
    )
    if "simulasi_fiskal_editor_version" not in st.session_state:
        st.session_state["simulasi_fiskal_editor_version"] = 0
    if "simulasi_fiskal_draft" not in st.session_state:
        st.session_state["simulasi_fiskal_draft"] = get_simulasi_fiskal_df().copy()

    draft_df = st.session_state["simulasi_fiskal_draft"].copy()
    draft_df["indikator"] = SIMULASI_FISKAL_ROWS
    for col in SIMULASI_FISKAL_COLS:
        draft_df[col] = pd.to_numeric(draft_df.get(col, 0.0), errors="coerce").fillna(0.0)
    draft_df = draft_df[["indikator", *SIMULASI_FISKAL_COLS]].copy()

    editor_key = f"simulasi_fiskal_editor_{st.session_state['simulasi_fiskal_editor_version']}"
    edited_df = st.data_editor(
        draft_df,
        key=editor_key,
        hide_index=True,
        num_rows="fixed",
        disabled=["indikator"],
        use_container_width=False,
        width=760,
        column_config={
            "indikator": st.column_config.TextColumn("Simulasi Fiskal", width="medium"),
            "out_tw1": st.column_config.NumberColumn("Q1", format="%.2f", step=0.01, width="small"),
            "out_tw2": st.column_config.NumberColumn("Q2", format="%.2f", step=0.01, width="small"),
            "out_tw3": st.column_config.NumberColumn("Q3", format="%.2f", step=0.01, width="small"),
            "out_tw4": st.column_config.NumberColumn("Q4", format="%.2f", step=0.01, width="small"),
        },
    )
    edited_df = edited_df[["indikator", *SIMULASI_FISKAL_COLS]].copy()
    edited_df["indikator"] = SIMULASI_FISKAL_ROWS
    for c in SIMULASI_FISKAL_COLS:
        edited_df[c] = pd.to_numeric(edited_df[c], errors="coerce").fillna(0.0)

    st.session_state["simulasi_fiskal_draft"] = edited_df.copy()
    applied_df = get_simulasi_fiskal_df()
    has_pending = not edited_df[SIMULASI_FISKAL_COLS].reset_index(drop=True).equals(
        applied_df[SIMULASI_FISKAL_COLS].reset_index(drop=True)
    )

    c1, c2 = st.columns(2)
    if c1.button("Terapkan Simulasi Fiskal", use_container_width=True, type="primary"):
        st.session_state["simulasi_fiskal_df"] = edited_df.copy()
        st.session_state["simulasi_fiskal_draft"] = edited_df.copy()
        st.session_state["simulasi_fiskal_notice"] = ("success", "Simulasi fiskal berhasil diterapkan ke Tabel Utama.")
        st.rerun()
    if c2.button("Reset Simulasi Fiskal", use_container_width=True):
        reset_df = build_simulasi_fiskal_df()
        st.session_state["simulasi_fiskal_df"] = reset_df.copy()
        st.session_state["simulasi_fiskal_draft"] = reset_df.copy()
        st.session_state["simulasi_fiskal_editor_version"] += 1
        st.session_state["simulasi_fiskal_notice"] = ("success", "Simulasi fiskal telah di-reset.")
        st.rerun()

    st.caption(
        "Ada perubahan draft yang belum diterapkan ke Tabel Utama."
        if has_pending else
        "Draft simulasi fiskal sudah sinkron dengan Tabel Utama."
    )
    notice = st.session_state.pop("simulasi_fiskal_notice", None)
    if notice:
        level, msg = notice
        getattr(st, level if level in {"success", "warning", "error", "info"} else "info")(msg)
    return applied_df


def render_simulasi_makro_editor() -> pd.DataFrame:
    st.markdown("### Simulasi Asumsi Dasar Ekonomi Makro")
    st.caption(
        "Kolom APBN 2026 bersifat tetap, sedangkan kolom Shock dapat diisi untuk simulasi. "
        "Perubahan pada Pertumbuhan ekonomi (%) dan Inflasi (%) memengaruhi kolom Dampak pada "
        "'1. Penerimaan Perpajakan', sedangkan perubahan pada Tingkat bunga SUN 10 tahun memengaruhi "
        "kolom Dampak pada '1. Belanja Pemerintah Pusat'."
    )
    if "simulasi_makro_editor_version" not in st.session_state:
        st.session_state["simulasi_makro_editor_version"] = 0
    if "simulasi_makro_draft" not in st.session_state:
        st.session_state["simulasi_makro_draft"] = get_simulasi_makro_df().copy()

    draft_df = st.session_state["simulasi_makro_draft"].copy()
    draft_df["indikator"] = [row[0] for row in SIMULASI_MAKRO_DEFAULTS]
    draft_df["apbn_2026"] = [row[1] for row in SIMULASI_MAKRO_DEFAULTS]
    draft_df["shock"] = pd.to_numeric(draft_df.get("shock"), errors="coerce")
    draft_df = draft_df[["indikator", "apbn_2026", "shock"]].copy()

    editor_key = f"simulasi_makro_editor_{st.session_state['simulasi_makro_editor_version']}"
    edited_df = st.data_editor(
        draft_df,
        key=editor_key,
        hide_index=True,
        num_rows="fixed",
        disabled=["indikator", "apbn_2026"],
        use_container_width=True,
        column_config={
            "indikator": st.column_config.TextColumn("Asumsi Dasar Ekonomi Makro", width="large"),
            "apbn_2026": st.column_config.NumberColumn("APBN 2026", format="%.1f", step=0.1, width="small"),
            "shock": st.column_config.NumberColumn("Shock", format="%.1f", step=0.1, width="small"),
        },
    )
    edited_df = edited_df[["indikator", "apbn_2026", "shock"]].copy()
    edited_df["indikator"] = [row[0] for row in SIMULASI_MAKRO_DEFAULTS]
    edited_df["apbn_2026"] = [row[1] for row in SIMULASI_MAKRO_DEFAULTS]
    edited_df["shock"] = pd.to_numeric(edited_df["shock"], errors="coerce")

    st.session_state["simulasi_makro_draft"] = edited_df.copy()
    applied_df = get_simulasi_makro_df()
    has_pending = not edited_df[["shock"]].reset_index(drop=True).equals(
        applied_df[["shock"]].reset_index(drop=True)
    )

    c1, c2 = st.columns(2)
    if c1.button("Terapkan Shock Makro", use_container_width=True, type="primary"):
        st.session_state["simulasi_makro_df"] = edited_df.copy()
        st.session_state["simulasi_makro_draft"] = edited_df.copy()
        st.session_state["simulasi_makro_notice"] = ("success", "Input shock makro berhasil disimpan.")
        st.rerun()
    if c2.button("Reset Shock Makro", use_container_width=True):
        reset_df = build_simulasi_makro_df()
        st.session_state["simulasi_makro_df"] = reset_df.copy()
        st.session_state["simulasi_makro_draft"] = reset_df.copy()
        st.session_state["simulasi_makro_editor_version"] += 1
        st.session_state["simulasi_makro_notice"] = ("success", "Kolom shock makro telah dikosongkan kembali.")
        st.rerun()

    st.caption(
        "Ada perubahan input shock makro yang belum diterapkan."
        if has_pending else
        "Input shock makro sudah sinkron."
    )

    preview = calculate_macro_fiskal_impacts(edited_df)
    revenue_preview = preview.get("revenue_total", 0.0)
    spending_preview = preview.get("spending_total", 0.0)
    st.info(
        "Aturan dampak aktif: "
        f"Pertumbuhan ekonomi ±0,1 => Penerimaan Perpajakan ±{fmt_fiskal_number(MACRO_FISKAL_RULES['Pertumbuhan ekonomi (%)']['coef_per_0_1'], 2)}; "
        f"Inflasi ±0,1 => Penerimaan Perpajakan ±{fmt_fiskal_number(MACRO_FISKAL_RULES['Inflasi (%)']['coef_per_0_1'], 2)}; "
        f"Tingkat bunga SUN 10 tahun ±0,1 => Belanja Pemerintah Pusat ±{fmt_fiskal_number(MACRO_FISKAL_RULES['Tingkat bunga SUN 10 tahun']['coef_per_0_1'], 2)}. "
        f"Preview draft saat ini: Dampak PP = {fmt_fiskal_number(revenue_preview, 2)}, "
        f"Dampak BPP = {fmt_fiskal_number(spending_preview, 2)}."
    )

    notice = st.session_state.pop("simulasi_makro_notice", None)
    if notice:
        level, msg = notice
        getattr(st, level if level in {"success", "warning", "error", "info"} else "info")(msg)
    return applied_df


def dataframe_for_display(df: pd.DataFrame, pct: bool = False, hide_rows=None) -> pd.DataFrame:
    view = df.copy()
    if hide_rows:
        view = view[~view["indikator"].isin(hide_rows)].copy()
    view = view[["indikator", *PERIOD_ORDER]].rename(columns={"indikator": "Indikator", **PERIOD_MAP})
    for c in view.columns[1:]:
        view[c] = view[c].apply(fmt_pct if pct else fmt_id0)
    return view


def render_table(df: pd.DataFrame, pct: bool = False, hide_rows=None):
    st.dataframe(dataframe_for_display(df, pct=pct, hide_rows=hide_rows), use_container_width=True, hide_index=True)


def _lookup_value(df: pd.DataFrame, indikator: str, col: str):
    if df is None or df.empty or "indikator" not in df.columns or col not in df.columns:
        return None
    mask = df["indikator"].astype(str).str.strip() == indikator
    if not mask.any():
        return None
    series = pd.to_numeric(df.loc[mask, col], errors="coerce")
    if series.empty:
        return None
    return series.iloc[0]


def build_main_comparison_df(
    baseline_df: pd.DataFrame,
    shock_fiskal_df: pd.DataFrame,
    shock_makro_df: Optional[pd.DataFrame] = None,
    formatter=fmt_id0,
) -> pd.DataFrame:
    baseline_df = ensure_schema(baseline_df, "pdb") if "indikator" in baseline_df.columns else baseline_df
    shock_fiskal_df = ensure_schema(shock_fiskal_df, "pdb") if "indikator" in shock_fiskal_df.columns else shock_fiskal_df
    if shock_makro_df is None:
        shock_makro_df = shock_fiskal_df.copy()
    else:
        shock_makro_df = ensure_schema(shock_makro_df, "pdb") if "indikator" in shock_makro_df.columns else shock_makro_df

    rows = []
    for indikator in PDB_MAIN_ROWS:
        row = {"Indikator": indikator}
        for col, label in PERIOD_MAP.items():
            if col == "full_year":
                row[f"{label} - Baseline"] = formatter(_lookup_value(baseline_df, indikator, col))
                row[f"{label} - Shock Fiskal"] = formatter(_lookup_value(shock_fiskal_df, indikator, col))
                row[f"{label} - Shock Makro"] = formatter(_lookup_value(shock_makro_df, indikator, col))
            else:
                row[f"{label} - Baseline"] = formatter(_lookup_value(baseline_df, indikator, col))
                row[f"{label} - Shock Fiskal"] = formatter(_lookup_value(shock_fiskal_df, indikator, col))
        rows.append(row)
    return pd.DataFrame(rows)


def render_main_comparison_table(
    baseline_df: pd.DataFrame,
    shock_fiskal_df: pd.DataFrame,
    shock_makro_df: Optional[pd.DataFrame] = None,
    formatter=fmt_id0,
    note_text: Optional[str] = None,
):
    out = build_main_comparison_df(
        baseline_df=baseline_df,
        shock_fiskal_df=shock_fiskal_df,
        shock_makro_df=shock_makro_df,
        formatter=formatter,
    )
    st.dataframe(out, use_container_width=True, hide_index=True)
    if note_text:
        st.caption(note_text)


def render_fiskal_block_table(simulasi_makro_df: Optional[pd.DataFrame] = None):
    impacts = calculate_macro_fiskal_impacts(simulasi_makro_df)
    dampak_pp = round(impacts.get("revenue_total", 0.0), 2)
    dampak_bpp = round(impacts.get("spending_total", 0.0), 2)

    apbn = {
        "pp": 2693714,
        "pnbp": 459200,
        "hibah": 666,
        "bpp": 3149733,
        "tkd": 692995,
    }
    dampak = {
        "pp": dampak_pp,
        "pnbp": 0.0,
        "hibah": 0.0,
        "bpp": dampak_bpp,
        "tkd": 0.0,
    }

    apbn_A = apbn["pp"] + apbn["pnbp"] + apbn["hibah"]
    apbn_B = apbn["bpp"] + apbn["tkd"]
    apbn_C = apbn_A - apbn_B
    apbn_D = -apbn_C

    dampak_A = dampak["pp"] + dampak["pnbp"] + dampak["hibah"]
    dampak_B = dampak["bpp"] + dampak["tkd"]
    dampak_C = dampak_A - dampak_B
    dampak_D = -dampak_C

    def outlook(a, d):
        return a + d

    fiskal_rows = [
        {"Uraian": "A. Pendapatan Negara dan Hibah", "APBN 2026": apbn_A, "Dampak": dampak_A, "Outlook": outlook(apbn_A, dampak_A)},
        {"Uraian": "1. Penerimaan Perpajakan", "APBN 2026": apbn["pp"], "Dampak": dampak["pp"], "Outlook": outlook(apbn["pp"], dampak["pp"])},
        {"Uraian": "2. Penerimaan Negara Bukan Pajak", "APBN 2026": apbn["pnbp"], "Dampak": dampak["pnbp"], "Outlook": outlook(apbn["pnbp"], dampak["pnbp"])},
        {"Uraian": "3. Hibah", "APBN 2026": apbn["hibah"], "Dampak": dampak["hibah"], "Outlook": outlook(apbn["hibah"], dampak["hibah"])},
        {"Uraian": "B. Belanja Negara", "APBN 2026": apbn_B, "Dampak": dampak_B, "Outlook": outlook(apbn_B, dampak_B)},
        {"Uraian": "1. Belanja Pemerintah Pusat", "APBN 2026": apbn["bpp"], "Dampak": dampak["bpp"], "Outlook": outlook(apbn["bpp"], dampak["bpp"])},
        {"Uraian": "2. Transfer ke Daerah", "APBN 2026": apbn["tkd"], "Dampak": dampak["tkd"], "Outlook": outlook(apbn["tkd"], dampak["tkd"])},
        {"Uraian": "C. Surplus/Defisit", "APBN 2026": apbn_C, "Dampak": dampak_C, "Outlook": outlook(apbn_C, dampak_C)},
        {"Uraian": "D. Pembiayaan Anggaran", "APBN 2026": apbn_D, "Dampak": dampak_D, "Outlook": outlook(apbn_D, dampak_D)},
    ]

    tbl = pd.DataFrame(fiskal_rows)
    tbl_display = tbl.copy()
    tbl_display["APBN 2026"] = tbl_display["APBN 2026"].apply(lambda x: fmt_fiskal_number(x, 0))
    tbl_display["Dampak"] = tbl_display["Dampak"].apply(lambda x: fmt_fiskal_number(x, 2))
    tbl_display["Outlook"] = tbl_display["Outlook"].apply(lambda x: fmt_fiskal_number(x, 2))
    st.dataframe(tbl_display, use_container_width=True, hide_index=True)

    rev_detail = impacts.get("revenue", {})
    spn_detail = impacts.get("spending", {})
    detail_lines = []
    if rev_detail:
        detail_lines.append("Rincian pembentuk Dampak pada '1. Penerimaan Perpajakan':")
        for name, val in rev_detail.items():
            detail_lines.append(f"- {name}: {fmt_fiskal_number(val, 2)}")
    if spn_detail:
        detail_lines.append("")
        detail_lines.append("Rincian pembentuk Dampak pada '1. Belanja Pemerintah Pusat':")
        for name, val in spn_detail.items():
            detail_lines.append(f"- {name}: {fmt_fiskal_number(val, 2)}")
    if detail_lines:
        st.caption("\n".join(detail_lines))


def make_history_chart(pdb_history: Optional[dict], selected_components):
    if not pdb_history or pdb_history.get("level") is None or pdb_history["level"].empty:
        st.info("Data historis PDB belum tersedia.")
        return
    plot_df = pdb_history["level"].copy()
    plot_df = plot_df[plot_df["komponen"].isin(selected_components)]
    fig = px.line(
        plot_df,
        x="tanggal",
        y="nilai",
        color="komponen",
        custom_data=["nilai_fmt"],
        color_discrete_sequence=[PRIMARY, ACCENT, SUCCESS, PURPLE, NEGATIVE, "#F4A261", "#4C78A8", "#6C8EAD"],
    )
    fig.update_traces(mode="lines+markers", hovertemplate="%{x|%Y-%m-%d}<br>%{customdata[0]}")
    fig.update_layout(
        height=380,
        hovermode="x unified",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend_title_text="",
    )
    fig.update_yaxes(gridcolor=GRID)
    st.plotly_chart(fig, use_container_width=True)


def make_growth_chart(pdb_history: Optional[dict], selected_components, growth_col: str, title: str):
    if not pdb_history or pdb_history.get("growth") is None or pdb_history["growth"].empty:
        st.info("Data pertumbuhan PDB belum tersedia.")
        return
    plot_df = pdb_history["growth"].copy()
    plot_df = plot_df[plot_df["komponen"].isin(selected_components)]
    plot_df["fmt"] = plot_df[growth_col].apply(fmt_pct)
    fig = px.line(
        plot_df,
        x="tanggal",
        y=growth_col,
        color="komponen",
        custom_data=["fmt"],
        color_discrete_sequence=[SUCCESS, ACCENT, PRIMARY, PURPLE, NEGATIVE, "#F4A261", "#4C78A8", "#6C8EAD"],
    )
    fig.update_traces(mode="lines+markers", hovertemplate="%{x|%Y-%m-%d}<br>%{customdata[0]}")
    fig.update_layout(
        title=title,
        height=380,
        hovermode="x unified",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend_title_text="",
    )
    fig.update_yaxes(gridcolor=GRID, zeroline=True)
    st.plotly_chart(fig, use_container_width=True)


# ===== Main App =====
workbook, pdb_history, pdb_tables, source_status = load_dashboard_data()

st.sidebar.markdown("## Pengaturan Dashboard")
show_preview = st.sidebar.toggle("Tampilkan preview data mentah", value=False)
st.sidebar.markdown("### Sumber Data")
st.sidebar.info(source_status)

st.title("Dashboard Pemantauan PDB")
st.markdown("---")
st.info(source_status)

simulasi_fiskal_df = get_simulasi_fiskal_df()
simulasi_makro_df = get_simulasi_makro_df()

baseline_pdb_nominal = ensure_full_year_from_quarters(workbook["pdb"])
adjusted_pdb_nominal = apply_simulasi_fiskal_to_pdb_nominal(baseline_pdb_nominal.copy(), simulasi_fiskal_df)

baseline_top_yoy = pdb_tables["yoy"] if pdb_tables else empty_df("pdb")
baseline_top_qtq = pdb_tables["qtq"] if pdb_tables else empty_df("pdb")
adjusted_top_tables = build_adjusted_top_growth_tables(pdb_history, adjusted_pdb_nominal)
adjusted_top_yoy = adjusted_top_tables.get("yoy", empty_df("pdb"))
adjusted_top_qtq = adjusted_top_tables.get("qtq", empty_df("pdb"))

st.markdown("## Tabel Utama — Blok Accounting")
st.caption(
    "Tampilan utama menggunakan layout tabel datar. Kolom Shock Makro pada tabel utama masih mengikuti Shock Fiskal. "
    "Input asumsi shock makro sudah dihubungkan ke Blok Fiskal untuk menghitung dampak fiskal."
)

top_nominal_tab, top_yoy_tab, top_qtq_tab = st.tabs([
    "Tabel Nominal 2026",
    "Tabel Year on Year (YoY)",
    "Tabel Quarter to Quarter (QtQ)",
])

with top_nominal_tab:
    render_main_comparison_table(
        baseline_df=baseline_pdb_nominal,
        shock_fiskal_df=adjusted_pdb_nominal,
        shock_makro_df=adjusted_pdb_nominal,
        formatter=fmt_id0,
        note_text="Kolom Shock Makro pada tabel utama masih mengikuti Shock Fiskal.",
    )
with top_yoy_tab:
    render_main_comparison_table(
        baseline_df=baseline_top_yoy,
        shock_fiskal_df=adjusted_top_yoy,
        shock_makro_df=adjusted_top_yoy,
        formatter=fmt_pct,
        note_text="Tabel YoY menggunakan hasil pertumbuhan dari baseline dan penyesuaian shock fiskal.",
    )
with top_qtq_tab:
    render_main_comparison_table(
        baseline_df=baseline_top_qtq,
        shock_fiskal_df=adjusted_top_qtq,
        shock_makro_df=adjusted_top_qtq,
        formatter=fmt_pct,
        note_text="Tabel QtQ menggunakan hasil pertumbuhan dari baseline dan penyesuaian shock fiskal.",
    )

simulasi_fiskal_df = render_simulasi_fiskal_editor()
makro_tab, pdb_tab, moneter_tab, fiskal_tab = st.tabs(["Blok Makro", "Blok Accounting", "Blok Moneter", "Blok Fiskal"])

with makro_tab:
    st.markdown("## Blok Makro")
    render_table(workbook["makro"])

with pdb_tab:
    st.markdown("## Accounting / PDB")
    nominal_tab, yoy_tab, qtq_tab = st.tabs(["Tabel Nominal 2026", "Tabel Year on Year (YoY)", "Tabel Quarter to Quarter (QtQ)"])
    with nominal_tab:
        render_table(workbook["pdb"])
    with yoy_tab:
        render_table(
            pdb_tables["yoy"][~pdb_tables["yoy"]["indikator"].isin(EXCLUDE_GROWTH_ROWS)] if pdb_tables else empty_df("pdb"),
            pct=True,
        )
    with qtq_tab:
        render_table(
            pdb_tables["qtq"][~pdb_tables["qtq"]["indikator"].isin(EXCLUDE_GROWTH_ROWS)] if pdb_tables else empty_df("pdb"),
            pct=True,
        )

    selected_components = st.multiselect(
        "Pilih komponen historis yang ingin ditampilkan",
        options=PDB_COMPONENTS,
        default=PDB_COMPONENTS,
    )
    selected_components = selected_components or PDB_COMPONENTS
    hist_tab, yoyc_tab, qtqc_tab = st.tabs(["Historis Level", "Year on Year (YoY)", "Quarter to Quarter (QtQ)"])
    with hist_tab:
        make_history_chart(pdb_history, selected_components)
    with yoyc_tab:
        make_growth_chart(
            pdb_history,
            [c for c in selected_components if c not in EXCLUDE_GROWTH_ROWS],
            "yoy",
            "Pertumbuhan Year on Year (YoY)",
        )
    with qtqc_tab:
        make_growth_chart(
            pdb_history,
            [c for c in selected_components if c not in EXCLUDE_GROWTH_ROWS],
            "qtq",
            "Pertumbuhan Quarter to Quarter (QtQ)",
        )

with moneter_tab:
    st.markdown("## Blok Moneter")
    render_table(workbook["moneter"])

with fiskal_tab:
    st.markdown("## Blok Fiskal")
    render_fiskal_block_table(simulasi_makro_df)
    st.markdown("---")
    simulasi_makro_df = render_simulasi_makro_editor()

if show_preview:
    with st.expander("Preview data yang berhasil dimuat", expanded=False):
        st.markdown("### Preview simulasi fiskal editable")
        st.dataframe(simulasi_fiskal_df, use_container_width=True, hide_index=True)
        st.markdown("### Preview baseline PDB nominal")
        st.dataframe(baseline_pdb_nominal, use_container_width=True, hide_index=True)
        st.markdown("### Preview shock fiskal / shock makro PDB nominal")
        st.dataframe(adjusted_pdb_nominal, use_container_width=True, hide_index=True)
        st.markdown("### Preview baseline YoY")
        st.dataframe(baseline_top_yoy, use_container_width=True, hide_index=True)
        st.markdown("### Preview shock fiskal / shock makro YoY")
        st.dataframe(adjusted_top_yoy, use_container_width=True, hide_index=True)
        st.markdown("### Preview baseline QtQ")
        st.dataframe(baseline_top_qtq, use_container_width=True, hide_index=True)
        st.markdown("### Preview shock fiskal / shock makro QtQ")
        st.dataframe(adjusted_top_qtq, use_container_width=True, hide_index=True)
        st.markdown("### Preview input shock makro")
        st.dataframe(simulasi_makro_df, use_container_width=True, hide_index=True)
        if pdb_history:
            st.markdown("### Preview historis komponen PDB")
            st.dataframe(pdb_history["level"], use_container_width=True, hide_index=True)
            st.markdown("### Preview pertumbuhan komponen PDB")
            st.dataframe(pdb_history["growth"], use_container_width=True, hide_index=True)
