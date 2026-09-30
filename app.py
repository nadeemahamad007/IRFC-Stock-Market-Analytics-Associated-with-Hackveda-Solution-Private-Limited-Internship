from __future__ import annotations

from pathlib import Path
import io

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ---------------------------------------------------------------------
# App configuration
# ---------------------------------------------------------------------
st.set_page_config(
    page_title="IRFC | Stock Market Analytics",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

DATA_PATH = Path(__file__).parent / "data" / "IRFC_BSE_Data.csv"
REQUIRED_COLUMNS = ["date", "open", "high", "low", "close", "volume"]


# ---------------------------------------------------------------------
# Data loading and validation
# ---------------------------------------------------------------------
@st.cache_data(show_spinner="Loading and validating historical data…")
def load_data(file_bytes: bytes | None = None) -> pd.DataFrame:
    """Load the bundled CSV or a user-uploaded CSV and normalize its schema."""
    if file_bytes is None:
        if not DATA_PATH.exists():
            raise FileNotFoundError(
                f"Dataset not found at {DATA_PATH}. Add the CSV to the data/ folder."
            )
        frame = pd.read_csv(DATA_PATH)
    else:
        frame = pd.read_csv(io.BytesIO(file_bytes))

    # Accept the original Alpha Vantage column names as well as normalized names.
    rename_map = {
        "Unnamed: 0": "date",
        "timestamp": "date",
        "1. open": "open",
        "2. high": "high",
        "3. low": "low",
        "4. close": "close",
        "5. volume": "volume",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
        "Date": "date",
        "Timestamp": "date",
    }
    frame = frame.rename(columns=rename_map)
    frame.columns = [str(c).strip().lower() for c in frame.columns]

    missing = [c for c in REQUIRED_COLUMNS if c not in frame.columns]
    if missing:
        raise ValueError(
            "The file is missing required column(s): "
            + ", ".join(missing)
            + ". Expected date, open, high, low, close, volume."
        )

    frame = frame[REQUIRED_COLUMNS].copy()
    # Supports ISO dates and common day-first dates from the original export.
    parsed = pd.to_datetime(frame["date"], errors="coerce", dayfirst=True)
    frame["date"] = parsed
    for col in ["open", "high", "low", "close", "volume"]:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")

    frame = frame.dropna(subset=REQUIRED_COLUMNS)
    frame = frame.drop_duplicates(subset=["date"], keep="last")
    frame = frame.sort_values("date").reset_index(drop=True)
    frame["volume"] = frame["volume"].round().astype("int64")

    # Keep only structurally valid OHLC records.
    valid_ohlc = (
        (frame["high"] >= frame[["open", "close", "low"]].max(axis=1))
        & (frame["low"] <= frame[["open", "close", "high"]].min(axis=1))
        & (frame[["open", "high", "low", "close"]] > 0).all(axis=1)
        & (frame["volume"] >= 0)
    )
    frame = frame.loc[valid_ohlc].copy()

    frame["daily_return_pct"] = frame["close"].pct_change() * 100
    frame["daily_change"] = frame["close"].diff()
    frame["ma_20"] = frame["close"].rolling(20, min_periods=1).mean()
    frame["ma_50"] = frame["close"].rolling(50, min_periods=1).mean()
    frame["ma_200"] = frame["close"].rolling(200, min_periods=1).mean()
    frame["year"] = frame["date"].dt.year
    frame["month"] = frame["date"].dt.to_period("M").astype(str)
    frame["daily_range_pct"] = (
        (frame["high"] - frame["low"]) / frame["open"].replace(0, np.nan) * 100
    )
    return frame


# ---------------------------------------------------------------------
# Page header
# ---------------------------------------------------------------------
st.title("📈 IRFC Stock Market Analytics")
st.caption(
    "Historical price, trading-volume, volatility, and trend exploration "
    "for Indian Railway Finance Corporation (IRFC)."
)

with st.sidebar:
    st.header("Controls")
    uploaded = st.file_uploader(
        "Use another CSV (optional)",
        type=["csv"],
        help="Expected columns: date, open, high, low, close, volume. "
             "Original Alpha Vantage column names are also supported.",
    )
    try:
        data = load_data(uploaded.getvalue() if uploaded else None)
    except Exception as exc:
        st.error(f"Could not load the dataset: {exc}")
        st.stop()

    min_date = data["date"].min().date()
    max_date = data["date"].max().date()
    selected_dates = st.date_input(
        "Date range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
        help="Choose the period to include in the dashboard.",
    )
    if isinstance(selected_dates, tuple) and len(selected_dates) == 2:
        start_date, end_date = selected_dates
    else:
        start_date = end_date = selected_dates

    st.divider()
    st.caption("Dataset")
    st.write(f"**{len(data):,}** valid trading-day records")
    st.write(f"{min_date:%d %b %Y} – {max_date:%d %b %Y}")

filtered = data[
    data["date"].dt.date.between(start_date, end_date)
].copy()

if filtered.empty:
    st.warning("No records found for the selected date range. Adjust the dates.")
    st.stop()

# ---------------------------------------------------------------------
# KPI cards
# ---------------------------------------------------------------------
first_close = filtered.iloc[0]["close"]
last_close = filtered.iloc[-1]["close"]
period_change = last_close - first_close
period_return = (last_close / first_close - 1) * 100 if first_close else np.nan
latest = filtered.iloc[-1]
prior_close = filtered.iloc[-2]["close"] if len(filtered) > 1 else np.nan
latest_change_pct = (
    (latest["close"] / prior_close - 1) * 100
    if pd.notna(prior_close) and prior_close
    else np.nan
)
avg_volume = filtered["volume"].mean()
period_high = filtered["high"].max()
period_low = filtered["low"].min()

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Latest close in range", f"₹{last_close:,.2f}", f"{latest_change_pct:+.2f}%" if pd.notna(latest_change_pct) else None)
k2.metric("Period return", f"{period_return:+.2f}%", f"₹{period_change:+,.2f}")
k3.metric("Period high", f"₹{period_high:,.2f}")
k4.metric("Period low", f"₹{period_low:,.2f}")
k5.metric("Avg. daily volume", f"{avg_volume:,.0f}")

st.caption(
    f"Selected period: **{start_date:%d %b %Y} – {end_date:%d %b %Y}** · "
    f"{len(filtered):,} records. Values are descriptive historical statistics, "
    "not investment advice."
)

# ---------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------
tab_overview, tab_prices, tab_volume, tab_returns, tab_data = st.tabs(
    ["Overview", "Price trends", "Volume", "Returns & risk", "Data & quality"]
)

with tab_overview:
    left, right = st.columns([1.6, 1])
    with left:
        st.subheader("Closing price over time")
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=filtered["date"], y=filtered["close"],
            mode="lines", name="Close",
            line=dict(width=2),
            hovertemplate="%{x|%d %b %Y}<br>Close: ₹%{y:,.2f}<extra></extra>",
        ))
        fig.update_layout(
            height=390, margin=dict(l=10, r=10, t=20, b=10),
            xaxis_title=None, yaxis_title="Price (₹)",
            hovermode="x unified", legend=dict(orientation="h", y=1.08),
        )
        st.plotly_chart(fig, use_container_width=True)
    with right:
        st.subheader("Monthly closing price")
        monthly = (
            filtered.set_index("date")["close"]
            .resample("ME").last().dropna().rename("close").reset_index()
        )
        if not monthly.empty:
            fig_month = px.bar(
                monthly, x="date", y="close",
                labels={"date": "Month", "close": "Month-end close (₹)"},
            )
            fig_month.update_layout(
                height=390, margin=dict(l=10, r=10, t=20, b=10),
                xaxis_title=None, yaxis_title="Price (₹)",
            )
            st.plotly_chart(fig_month, use_container_width=True)
        else:
            st.info("Not enough data for monthly aggregation.")

    st.subheader("OHLC price range")
    candle = go.Figure(data=[go.Candlestick(
        x=filtered["date"],
        open=filtered["open"], high=filtered["high"],
        low=filtered["low"], close=filtered["close"],
        name="IRFC",
    )])
    candle.update_layout(
        height=470, margin=dict(l=10, r=10, t=20, b=10),
        xaxis_title=None, yaxis_title="Price (₹)",
        xaxis_rangeslider_visible=False,
    )
    st.plotly_chart(candle, use_container_width=True)

with tab_prices:
    st.subheader("Closing price with moving averages")
    price_fig = go.Figure()
    price_fig.add_trace(go.Scatter(x=filtered["date"], y=filtered["close"], name="Close", mode="lines"))
    # Recompute moving averages on full history before applying the date filter,
    # so a selected range still has valid lookback context.
    for col, label in [("ma_20", "20-day MA"), ("ma_50", "50-day MA"), ("ma_200", "200-day MA")]:
        price_fig.add_trace(go.Scatter(x=filtered["date"], y=filtered[col], name=label, mode="lines"))
    price_fig.update_layout(
        height=520, hovermode="x unified",
        margin=dict(l=10, r=10, t=20, b=10),
        xaxis_title=None, yaxis_title="Price (₹)",
        legend=dict(orientation="h", y=1.08),
    )
    st.plotly_chart(price_fig, use_container_width=True)
    st.info("Moving averages are rolling historical summaries, not forecasts or buy/sell signals.")

with tab_volume:
    st.subheader("Daily trading volume")
    volume_fig = px.bar(
        filtered, x="date", y="volume",
        labels={"date": "Date", "volume": "Shares traded"},
        hover_data={"volume": ":,"},
    )
    volume_fig.update_layout(
        height=430, margin=dict(l=10, r=10, t=20, b=10),
        xaxis_title=None, yaxis_title="Volume (shares)",
    )
    st.plotly_chart(volume_fig, use_container_width=True)

    volume_by_month = (
        filtered.set_index("date")["volume"]
        .resample("ME").sum().rename("volume").reset_index()
    )
    st.subheader("Monthly trading volume")
    monthly_vol_fig = px.bar(
        volume_by_month, x="date", y="volume",
        labels={"date": "Month", "volume": "Total monthly volume"},
    )
    monthly_vol_fig.update_layout(
        height=350, margin=dict(l=10, r=10, t=20, b=10),
        xaxis_title=None, yaxis_title="Shares traded",
    )
    st.plotly_chart(monthly_vol_fig, use_container_width=True)

with tab_returns:
    st.subheader("Daily percentage returns")
    returns = filtered.dropna(subset=["daily_return_pct"])
    if not returns.empty:
        ret_fig = px.histogram(
            returns, x="daily_return_pct", nbins=50,
            labels={"daily_return_pct": "Daily return (%)"},
        )
        ret_fig.update_layout(
            height=350, margin=dict(l=10, r=10, t=20, b=10),
            yaxis_title="Trading days",
        )
        st.plotly_chart(ret_fig, use_container_width=True)

    st.subheader("Return and drawdown profile")
    risk = filtered[["date", "close"]].copy()
    risk["return_pct"] = risk["close"].pct_change() * 100
    risk["running_peak"] = risk["close"].cummax()
    risk["drawdown_pct"] = (risk["close"] / risk["running_peak"] - 1) * 100
    r1, r2 = st.columns(2)
    with r1:
        st.metric("Daily return volatility (std.)", f"{risk['return_pct'].std():.2f}%" if risk["return_pct"].notna().any() else "—")
    with r2:
        st.metric("Maximum drawdown in selected range", f"{risk['drawdown_pct'].min():.2f}%")
    dd_fig = px.area(
        risk, x="date", y="drawdown_pct",
        labels={"date": "Date", "drawdown_pct": "Drawdown from running peak (%)"},
    )
    dd_fig.update_layout(
        height=350, margin=dict(l=10, r=10, t=20, b=10),
        xaxis_title=None,
    )
    st.plotly_chart(dd_fig, use_container_width=True)
    st.caption("Returns and drawdowns are calculated from closing prices in the selected period.")

with tab_data:
    st.subheader("Filtered records")
    display = filtered[[
        "date", "open", "high", "low", "close", "volume",
        "daily_change", "daily_return_pct", "ma_20", "ma_50", "ma_200",
    ]].copy()
    display["date"] = display["date"].dt.strftime("%Y-%m-%d")
    st.dataframe(
        display.sort_values("date", ascending=False),
        use_container_width=True, hide_index=True,
    )
    csv_bytes = display.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Download filtered data (CSV)",
        data=csv_bytes,
        file_name="irfc_filtered_market_data.csv",
        mime="text/csv",
    )

    st.subheader("Data quality checks")
    q1, q2, q3, q4 = st.columns(4)
    q1.metric("Rows shown", f"{len(filtered):,}")
    q2.metric("Missing values", f"{int(filtered[REQUIRED_COLUMNS].isna().sum().sum()):,}")
    q3.metric("Duplicate dates", f"{int(filtered['date'].duplicated().sum()):,}")
    invalid = (
        (filtered["high"] < filtered[["open", "close", "low"]].max(axis=1))
        | (filtered["low"] > filtered[["open", "close", "high"]].min(axis=1))
        | (filtered[["open", "high", "low", "close"]] <= 0).any(axis=1)
        | (filtered["volume"] < 0)
    )
    q4.metric("Invalid OHLC rows", f"{int(invalid.sum()):,}")
    st.caption(
        "The app drops rows with missing required values, removes duplicate dates "
        "and excludes structurally invalid OHLC rows during loading."
    )

st.divider()
st.caption(
    "Educational analytics project. Historical data may contain provider-specific "
    "adjustments or limitations. This dashboard is not financial advice and does "
    "not provide investment recommendations."
)
