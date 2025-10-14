import asyncio
import json
from datetime import datetime, timezone
import websockets 

BINANCE_WS = "wss://stream.binance.com:9443/ws"
SYMBOL = "BTCUSDT"


# produce prices as they arrive
async def stream_latest_price(symbol: str):
    """
    Connect to Binance spot WS for 24h ticker updates and 
    yield the latest last price ('c').
    """
    stream = "{}/{}@ticker".format(BINANCE_WS, symbol.lower())
    backoff = 1

    while True:
        try:
            # open the WebSocket connection to the stream URL
            async with websockets.connect(stream, ping_interval = 20, ping_timeout = 20) as ws:
                backoff = 1 # reset after successful connect

                # every new message from Binance arrives as a string (JSON text)
                async for msg in ws: 
                    data = json.loads(msg) # turn the JSON string into a Python dictionary
                    price = float(data["c"]) # get the last price string from "c" key and convert it into float
                    yield price
        except (websockets.exceptions.ConnectionClosedError,
                websockets.exceptions.ConnectionClosedOK,
                websockets.exceptions.InvalidStatusCode,
                OSError):
            # if connection fails, wait backoff seconds before trying to reconnect
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 32) # double the wait time each failure, but cap it with 32 seconds


# listen to price, store only the latest price, and prints once per second            
async def print_price_every_second(symbol: str = SYMBOL):
    latest_price = None
    price_queue = asyncio.Queue(maxsize = 1) # A tiny queue that can hold at most one price. If new one comes and the queue is full, drop the old one and keep the new one


    # listen for incoming prices and keep the queue updated to the newest one
    async def update_price():
        # get price from the async generator every time it yields a price
        async for price in stream_latest_price(symbol):
            # keep only the latest price (drop older if the queue is full)
            try:
                price_queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            await price_queue.put(price)
    

    # print the most recent price once per second
    async def print_price():
        nonlocal latest_price

        while True:
            try:
                latest_price = price_queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            
            ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
            if latest_price == None:
                print(f"{ts} {symbol}: waiting for first tick...")
            else:
                print(f"{ts} {symbol}: {latest_price:.2f}")
            
            await asyncio.sleep(1)
    

    await asyncio.gather(update_price(), print_price())


if __name__ == "__main__":
    asyncio.run(print_price_every_second())