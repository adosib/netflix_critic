import os
import json
import timeit
import asyncio
import logging
from uuid import uuid4
from pathlib import Path

import aiohttp
import aiofiles
import requests

TOKEN = os.getenv("BRD_TOKEN")
DOWNLOADS = Path("/Users/asibalo/Downloads")

URLS = [
    "https://www.google.com/search?q=W.A.G.s+to+Riches+%28tv+series%29+reviews",
    "https://www.google.com/search?q=%22XO%2C+Kitty%22+tv+series+%282023%29",
    "https://www.google.com/search?q=%22Castlevania%3A+Nocturne%22+tv+series+%282023%29",
    "https://www.google.com/search?q=%22Hotel+Transylvania+2%22+movie+%282015%29",
    "https://www.google.com/search?q=Back+in+Action+%28movie%29",
]


async def get_data(httpsession, url):
    url += "&brd_json=html&gl=us&hl=en&num=100"
    async with httpsession.post(
        "https://api.brightdata.com/request",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {TOKEN}",
        },
        json={
            "zone": "serp_api1",
            "url": url,
            "format": "raw",
        },
    ) as r:
        json_body = await r.text()
        if not json_body:
            return ""
        return json.loads(json_body)["html"]


async def save_response_body(response_body: str, saveto_path: str):
    if not response_body:
        return
    async with aiofiles.open(str(saveto_path), "w+") as f:
        await f.write(response_body)


async def process(httpsession, url):
    logging.info(url)
    html = await get_data(httpsession, url)
    path = DOWNLOADS / f"{uuid4()}.html"
    await save_response_body(html, path)


async def main():
    sessions = [aiohttp.ClientSession() for _ in range(5)]
    try:
        async with asyncio.TaskGroup() as tg:
            for httpsession, url in zip(sessions, URLS):
                tg.create_task(process(httpsession, url))
    finally:
        for session in sessions:
            await session.close()


def run_async():
    asyncio.run(main())


def run_sync():
    with requests.Session() as session:
        for url in URLS:
            url += "&brd_json=html&gl=us&hl=en&num=100"
            response = session.post(
                "https://api.brightdata.com/request",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {TOKEN}",
                },
                json={
                    "zone": "serp_api1",
                    "url": url,
                    "format": "raw",
                },
            )

            if response.status_code != 200:
                raise RuntimeError(
                    f"Request failed with status code {response.status_code}: {response.text}"
                )

            response_json = response.json()
            html = response_json["html"]
            saveto_path = DOWNLOADS / f"{uuid4()}.html"
            with open(saveto_path, "w+") as f:
                f.write(html)


if __name__ == "__main__":
    for fn in [run_sync, run_async]:
        # Measure runtime with timeit
        elapsed_time = timeit.timeit(fn, number=1)
        print(f"Elapsed time: {elapsed_time:.4f} seconds")
