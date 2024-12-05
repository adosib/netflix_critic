###############
# 🛑
# Abandoned.
# This script is worthless.
# bun runtime doesn't have a jsdom package.
# Sticking with Node.
# See note in evaluate-bun.js script.
# 🛑
###############

import time
import asyncio
import logging
import cProfile
from typing import Literal
from pathlib import Path

THIS_DIR = Path(__file__).parent
JS_EVAL_SCRIPT = (THIS_DIR / ".." / ".." / "evaluate.js").resolve()
ROOT_DIR, *_ = [
    parent for parent in THIS_DIR.parents if parent.stem == "netflix_critic"
]

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)


async def extract_netflix_context(runtime: Literal["node", "bun"], html_path):
    logging.info(f"Attempting to extract context from {html_path}")
    process = await asyncio.create_subprocess_exec(
        runtime,
        JS_EVAL_SCRIPT,
        html_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await process.communicate()

    if process.returncode == 0:
        return stdout.decode()
    else:
        logging.error(stderr)
        return None


async def profile_runtime(runtime):
    start_time = time.perf_counter()

    async with asyncio.TaskGroup() as tg:
        for html_path in list(Path(ROOT_DIR / "data" / "raw" / "title").glob("*.html"))[
            :30
        ]:
            tg.create_task(extract_netflix_context(runtime, html_path))

    end_time = time.perf_counter()
    elapsed_time = end_time - start_time
    print(f"Total time taken for {runtime}: {elapsed_time:.2f} seconds")


async def main():
    # Run tasks for both Node.js and Bun runtimes concurrently
    await asyncio.gather(profile_runtime("node"), profile_runtime("bun"))


asyncio.run(main())
