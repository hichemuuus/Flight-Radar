from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx
import time
import asyncio
import random
from dotenv import load_dotenv
import os

load_dotenv()

OPENSKY_USER = os.getenv("OPENSKY_USER")
OPENSKY_PASS = os.getenv("OPENSKY_PASS")
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

cache = {"data": None, "timestamp": 0}
lock = asyncio.Lock()
TTL = 60


async def fetch_flights():
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                "https://opensky-network.org/api/states/all",
                auth=(OPENSKY_USER, OPENSKY_PASS)
            )
            if r.status_code == 429:
                return None
            r.raise_for_status()
            return r.json()
    except httpx.ConnectTimeout:
        print("OpenSky connection timed out")
        return None
    except httpx.HTTPError as e:
        print(f"HTTP error: {e}")
        return None


@app.get("/flights")
async def get_flights():
    now = time.time()

    async with lock:
        if cache["data"] and (now - cache["timestamp"]) < TTL:
            return cache["data"]

        raw = await fetch_flights()

        if raw is None:
            # Rate limited — retourne le cache même s'il est vieux
            if cache["data"]:
                return cache["data"]
            return {"count": 0, "flights": [], "error": "rate_limited"}

        data = transform(raw)
        cache["data"] = data
        cache["timestamp"] = time.time()

        return cache["data"]


def transform(raw):
    flights = []

    for plane in raw.get("states", []):
        if plane[5] is None or plane[6] is None:
            continue

        flights.append({
            "icao": plane[0],
            "callsign": plane[1].strip() if plane[1] else "N/A",
            "country": plane[2],
            "lon": plane[5],
            "lat": plane[6],
            "altitude": plane[7] or 0,
            "on_ground": plane[8],
            "speed": round(plane[9] * 3.6) if plane[9] else 0,
            "heading": plane[10] or 0,
        })

    return {"count": len(flights), "flights": flights}

@app.get("/flights/mock")
def get_mock_flights():
    countries = ["France", "Germany", "Algeria", "USA", "UK", "Spain", "Italy", "Morocco"]
    flights = []
    for i in range(200):
        flights.append({
            "icao": f"mock{i:04d}",
            "callsign": f"FL{random.randint(100,999)}",
            "country": random.choice(countries),
            "lon": random.uniform(-20, 50),
            "lat": random.uniform(20, 65),
            "altitude": random.choice([0, random.randint(1000, 13000)]),
            "on_ground": random.random() < 0.1,
            "speed": random.randint(200, 950),
            "heading": random.randint(0, 359),
        })
    return {"count": len(flights), "flights": flights}