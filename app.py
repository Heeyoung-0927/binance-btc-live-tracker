# import necessary Python packages

import asyncio
import threading
import time
import queue
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import bitcoin_current_price

# Page setup
st.set_page_config(page_title="Bitcoin Price - BTC/USDT (Binance)", layout="wide")
st.title("Bitcoin Spot Price - BTC/USDT (Binance)")
st.caption("Track last price from Binance 24h ticker stream using Binance Websocket API. Time shown in Eastern Time (ET).")

# Add Constants
WINDOW_SECS = 20 * 60   # 20-minute time window on the x-axis
REFRESH_SECONDS = 0.5
Y_TICK_INTERVAL = 250   # Fixes the y-axis tick spacing at 250 USDT (0.25k)
ET = ZoneInfo("America/New_York")   # A timezone object to convert from UTC timestamps to Eastern time for display

# Session State 
if "times" not in st.session_state:
    st.session_state.times = []
if "prices" not in st.session_state:
    st.session_state.prices = []

# Thread-safe queue (keeps only the freshest tick)
tick_queue: "queue.Queue[tuple[datetime, float]]" = queue.Queue(maxsize = 1)

# Background consumer to handle continuous data stream
def _bg_runner(symbol: str):
    # async function to fetch data from the WebSocket
    async def consume():
        async for price in bitcoin_current_price.stream_latest_price(symbol):
            ts = datetime.now(timezone.utc)     # current time in UTC
            try:
                while True:
                    tick_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                tick_queue.put_nowait((ts, price))
            except queue.Full:
                pass
    
    asyncio.run(consume())

@st.cache_resource
def start_background(symbol: str):
    t = threading.Thread(target=_bg_runner, args=(symbol,), daemon=True)
    t.start()
    return t

start_background(bitcoin_current_price.SYMBOL)

# Create the Plotly figure object only once
if "fig" not in st.session_state:
    fig = go.Figure()
    # main price line
    fig.add_trace(go.Scatter(x = [], y = [], mode = "lines", line = dict(width = 2), name = "BTC/USDT"))
    # endpoint marker
    fig.add_trace(go.Scatter(x = [], y = [], mode = "markers", marker = dict(size = 8), showlegend = False, name = "last"))

    fig.update_layout(
        uirevision = "btc-live",
        margin = dict(l = 60, r = 30, t = 30, b = 50),
        height = 460,
        xaxis = dict(title = "Time (ET)", showgrid = True, gridcolor = "rgba(255, 255, 255, 0.15)"),
        yaxis = dict(
            title = "BTC/USDT Price",
            showgrid = True,
            gridcolor = "rgba(255, 255, 255, 0.15)",
            tickformat = "~s",  # formats the axis labels in k (114000 -> 114k, 114250 -> 114.25k)
            dtick = Y_TICK_INTERVAL
        )
    )
    st.session_state.fig = fig

plot_area = st.empty()



# Live update loop that repeatedly fetches new data, cleans up old data, updates the plot, and then pauses briefly before doing it all over again
while True:
    updated = False

    # Attempt to get new time and price and add them to 
    try: 
        while True:
            ts_utc, p = tick_queue.get_nowait()
            st.session_state.times.append(ts_utc)
            st.session_state.prices.append(p)
            updated = True
    except queue.Empty:
        pass
    
    # Check if there's new data to show. If so, updates the plot
    if updated and st.session_state.prices:
        # gets the full list of timestamps and prices from the session_state to work with
        times_utc = st.session_state.times 
        prices = st.session_state.prices
        now_utc = datetime.now(timezone.utc)

        # X-axis range rule (If less than 20 minutes of data available, shows all data; otherwise, shows only the most recent 20 minutes)
        first_utc = times_utc[0]
        window = timedelta(seconds = WINDOW_SECS)
        if now_utc - first_utc < window:
            x_start_utc = first_utc
            x_end_utc = first_utc + window
        else:
            x_start_utc = now_utc - window
            x_end_utc = now_utc
        
        # Trim off old time and price data
        i = 0
        while i < len(times_utc) and times_utc[i] < x_start_utc:
            i += 1
        if i:
            st.session_state.times = times_utc[i:]
            st.session_state.prices = prices[i:]
            times_utc = st.session_steate.times
            prices = st.session_state.prices
        
        # Convert UTC times to Eastern Times for plotting
        times_et = [t.astimezone(ET) for t in times_utc]
        x_start_et = x_start_utc.astimezone(ET)
        x_end_et = x_end_utc.astimezone(ET)

        # Update plotly figure data
        fig = st.session_state.fig
        fig.data[0].x = times_et   
        fig.data[0].y = prices
        fig.data[1].x = times_et[-1:]
        fig.data[1].y = prices[-1:]

        # Update endpoint marker
        last_ts_et = times_et[-1]
        last_price = prices[-1]
        fig.update_layout(annotations=[
            dict(
                x = last_ts_et, y = last_price, xanchor = "left",
                xshift = 8, yshift = -6, showarrow = False,
                text = f"${last_price:,.2f}", font = dict(size = 14, color = "#1f77b4")
            )
        ])

        # Update x and y axis range
        fig.update_xaxes(range = [x_start_et, x_end_et])

        ymin = min(prices)
        ymax = max(prices)
        low = (int ((ymin - Y_TICK_INTERVAL) // Y_TICK_INTERVAL)) * Y_TICK_INTERVAL
        high = (int ((ymax + Y_TICK_INTERVAL + Y_TICK_INTERVAL - 1) // Y_TICK_INTERVAL)) * Y_TICK_INTERVAL
        fig.update_yaxes(range = [low, high])

        # Display the updated plot
        plot_area.plotly_chart(fig, use_container_width = True, config = {"displayModeBar": False})

    time.sleep(REFRESH_SECONDS)
