"""FX service: official exchange rates in RON per unit of foreign currency, with fallbacks.

Degradation order:
  1. BNR XML feed (https://www.bnr.ro/nbrfxrates.xml) - the legal reference in Romania
  2. ECB reference rates (EUR-based, RON cross rates computed) - official secondary source
  3. last good data (stale cache)
  4. static rates, clearly flagged
"""

import time
import xml.etree.ElementTree as ET

import httpx
from fastapi import FastAPI, HTTPException

BNR_URL = "https://www.bnr.ro/nbrfxrates.xml"
ECB_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
CACHE_SECONDS = 3600
STATIC_FALLBACK = {"EUR": 5.35, "USD": 4.8, "GBP": 6.4, "CHF": 5.8}

app = FastAPI(title="FX Service (BNR / ECB)", version="0.2.0")
_cache: dict = {"fetched_at": 0.0, "data": None}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_bnr(xml_text: str) -> dict:
    # Namespace is http://www.bnr.ro/xsd (older files) or https://www.bnr.ro/xsd (2026+): match on local names
    root = ET.fromstring(xml_text)
    cube = next(e for e in root.iter() if _local(e.tag) == "Cube")
    rates = {}
    for r in cube:
        if _local(r.tag) == "Rate":
            rates[r.get("currency")] = round(float(r.text) / int(r.get("multiplier", "1")), 6)
    return {"date": cube.get("date"), "rates": rates, "source": "BNR"}


def parse_ecb(xml_text: str) -> dict:
    root = ET.fromstring(xml_text)
    day = next(e for e in root.iter() if _local(e.tag) == "Cube" and e.get("time"))
    per_eur = {c.get("currency"): float(c.get("rate")) for c in day if c.get("currency")}
    ron_per_eur = per_eur["RON"]
    rates = {"EUR": round(ron_per_eur, 6)}
    for cur, value in per_eur.items():
        if cur != "RON":
            rates[cur] = round(ron_per_eur / value, 6)
    return {"date": day.get("time"), "rates": rates, "source": "ECB (BNR unavailable; RON rate computed via EUR)"}


async def fetch_fresh() -> tuple[dict | None, list[str]]:
    errors = []
    async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
        for name, url, parser in (("BNR", BNR_URL, parse_bnr), ("ECB", ECB_URL, parse_ecb)):
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                if "xml" not in resp.headers.get("content-type", ""):
                    raise ValueError(f"non-XML response ({resp.headers.get('content-type')}, final url {resp.url})")
                return parser(resp.text), errors
            except Exception as e:
                errors.append(f"{name}: {e}")
    return None, errors


async def get_rates() -> dict:
    if _cache["data"] and time.time() - _cache["fetched_at"] < CACHE_SECONDS:
        return {**_cache["data"], "source": _cache["data"]["source"] + " (cache)"}
    data, errors = await fetch_fresh()
    if data:
        _cache.update(fetched_at=time.time(), data=data)
        return {**data, **({"warning": "; ".join(errors)} if errors else {})}
    if _cache["data"]:
        return {**_cache["data"], "source": _cache["data"]["source"] + " (stale cache)", "warning": "; ".join(errors)}
    return {"date": None, "rates": STATIC_FALLBACK, "source": "STATIC FALLBACK - do not use in production",
            "warning": "; ".join(errors)}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/rates")
async def rates():
    return await get_rates()


@app.get("/rates/{currency}")
async def rate(currency: str):
    currency = currency.upper()
    data = await get_rates()
    if currency == "RON":
        return {"currency": "RON", "rate": 1.0, "date": data["date"], "source": data["source"]}
    if currency not in data["rates"]:
        raise HTTPException(status_code=404, detail=f"Currency {currency} is not quoted")
    return {"currency": currency, "rate": data["rates"][currency], "date": data["date"], "source": data["source"],
            **({"warning": data["warning"]} if "warning" in data else {})}
