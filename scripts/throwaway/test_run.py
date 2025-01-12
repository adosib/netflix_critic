import time
import asyncio
import logging
import argparse
import textwrap

import aiohttp
import psycopg
import requests
from aiolimiter import AsyncLimiter

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
)


async def get_netflix(session, limiter, nflx_id):
    async with limiter:
        async with session.get(
            f"http://localhost:8000/title/{nflx_id}.html"
        ) as response:
            await response.text()
            return response


async def main(args):
    background_tasks = set()
    responses = []

    # Limit to 50 req/s w/o bursting https://aiolimiter.readthedocs.io/en/latest/#bursting
    limiter = AsyncLimiter(1, 1 / 50.0)

    connector = aiohttp.TCPConnector(limit=args.limit, limit_per_host=args.limit)
    async with aiohttp.ClientSession(
        connector=connector, headers={"source-path": __file__}
    ) as session:
        max_connections = session._connector.limit
        logging.info(
            f"Preparing GET tasks with max connection limit of: {max_connections}"
        )
        # Prepare all tasks first, don't await them yet
        for i, (netflix_id, *_) in enumerate(NETFLIX_IDS, start=1):
            task = asyncio.create_task(
                get_netflix(session, limiter, netflix_id), name=str(netflix_id)
            )
            background_tasks.add(task)
            task.add_done_callback(background_tasks.discard)

            if max_connections:
                if i % max_connections == 0:
                    responses.extend(await asyncio.gather(*background_tasks))

        responses.extend(await asyncio.gather(*background_tasks))
        return responses


def test_async(args):
    start = time.perf_counter()
    responses = asyncio.run(main(args))
    end = time.perf_counter()
    print(f"async run took: {end - start:.2f}s")


def test_sync():
    start = time.perf_counter()
    responses = []
    with requests.Session() as session:
        for nflx_id, *_ in NETFLIX_IDS:
            responses.append(session.get(f"http://localhost:8000/title/{nflx_id}.html"))
    end = time.perf_counter()
    print(f"synchronous run took: {end - start:.2f}s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Test synchronous and async requests to local webserver"
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Concurrent connection limit"
    )
    args = parser.parse_args()
    with psycopg.Connection.connect(
        "dbname=postgres user=postgres", autocommit=True
    ) as dbconn:
        with dbconn.cursor() as dbcur:
            sql = textwrap.dedent("""
                SELECT DISTINCT titles.netflix_id
                FROM titles
                JOIN availability 
                    ON availability.netflix_id = titles.netflix_id
                WHERE availability.available = True
                LIMIT 1000;
            """)

            logging.info(f"Running query: {textwrap.indent(sql, ' '*3)}")

            NETFLIX_IDS = dbcur.execute(sql).fetchall()

    test_async(args)
    test_sync()
