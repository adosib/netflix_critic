import sys
import json
import asyncio
import logging
import itertools
from http import HTTPStatus
from uuid import uuid4
from typing import Any, Dict, Optional, Annotated
from pathlib import Path
from collections import defaultdict

import pythonmonkey as pm
from bs4 import BeautifulSoup
from models import Title, Rating, Availability
from fastapi import (
    Query,
    Depends,
    FastAPI,
    Request,
    Response,
    HTTPException,
    BackgroundTasks,
)
from pydantic import BaseModel
from sqlmodel import Session, select, create_engine
from sqlalchemy import func
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask
from starlette.middleware.cors import CORSMiddleware

from netflix_critic_data.scripts.database_setup.backfill_titles import (
    HTMLContent,
    get_field,
)
from netflix_critic_data.scripts.database_setup.populate_ratings import (
    get_ratings,
    get_serp_html,
)
from netflix_critic_data.scripts.database_setup.populate_availability import (
    SessionHandler,
    save_response_body,
)

THIS_DIR = Path(__file__).parent
ROOT_DIR, *_ = [
    parent for parent in THIS_DIR.parents if parent.stem == "netflix_critic"
]
DOWNLOADED_TITLEPAGES_DIR = ROOT_DIR / "netflix_critic_data" / "data" / "raw" / "title"
DATABASE_URL = "postgresql://localhost:5432/postgres"
STATUS_REASONS = {x.value: x.name for x in list(HTTPStatus)}

APIFY_SEMAPHORE = asyncio.Semaphore(32)


class JobStore:
    """Data structure to avoid re-processing title IDs that have been processed already."""

    def __init__(self):
        self._data = defaultdict(list)
        self._global_values = set()  # Set to enforce global uniqueness of values

    def add(self, key: Any, values: list):
        """Add a value to a key. Ensure global uniqueness."""
        if key not in self._data:
            self._data[key]

        for value in values:
            if value in self._global_values:
                continue

            self._data[key].append(value)
            self._global_values.add(value)

    def get(self, key):
        """Get all values associated with a key."""
        return self._data.get(key, [])

    def __setitem__(self, key, value):
        return self.add(key, value)

    def __getitem__(self, key):
        return self.get(key)

    def __repr__(self):
        return repr(self._data)


global_job_store = JobStore()


app = FastAPI()
app.mount("/title", StaticFiles(directory=DOWNLOADED_TITLEPAGES_DIR, html=True))
templates = Jinja2Templates(directory=THIS_DIR / "templates")

# Add CORS middleware to allow cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_credentials=False,
    allow_origins=["*"],  # Or more restricted origins like "https://www.netflix.com"
    allow_methods=["*"],  # Allow all methods (GET, POST, etc.)
    allow_headers=["*"],  # Allow all headers
    expose_headers=[
        "X-Requested-With",
        "X-HTTP-Method-Override",
        "Content-Type",
        "Accept",
        "Cache-Control",
        "Connection",
        "X-Accel-Buffering",
    ],
)


######################## https://stackoverflow.com/questions/70891687/how-do-i-get-my-fastapi-applications-console-log-in-json-format-with-a-differen/70899261#70899261
class CustomJSONFormatter(logging.Formatter):
    def __init__(self, fmt):
        super().__init__(fmt)

    def format(self, record):
        super().format(record)
        return json.dumps(get_log(record), indent=2)


def get_log(record):
    d = {
        "time": record.asctime,
        "process_name": record.processName,
        "process_id": record.process,
        "thread_name": record.threadName,
        "thread_id": record.thread,
        "level": record.levelname,
        "logger_name": record.name,
        "pathname": record.pathname,
        "line": record.lineno,
        "message": record.message,
    }

    if hasattr(record, "extra_info"):
        d["req"] = record.extra_info["req"]
        d["res"] = record.extra_info["res"]

    return d


def get_file_handler(
    formatter, filename=(ROOT_DIR / "logs" / f"{Path(__file__).stem}.log")
):
    file_handler = logging.handlers.RotatingFileHandler(filename)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    return file_handler


def get_stream_handler(formatter):
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(logging.DEBUG)
    stream_handler.setFormatter(formatter)
    return stream_handler


formatter = CustomJSONFormatter("%(asctime)s")
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(get_stream_handler(formatter))
logger.addHandler(get_file_handler(formatter))


async def get_extra_info(request: Request, response: Response):
    return {
        "req": {
            "url": request.url.path,
            "headers": dict(
                request.headers
            ),  # request.headers is supposed to be a mapping that handles duplicate keys so coercing to dict is prone to break but ¯\_(ツ)_/¯
            "method": request.method,
            "http_version": request.scope["http_version"],
            "original_url": request.url.path,
            "query": dict(request.query_params),
            "body": request.request_body,
        },
        "res": {
            "status_code": response.status_code,
            "status": STATUS_REASONS.get(response.status_code),
            "headers": dict(response.headers),
        },
    }


async def write_log_data(request, response):
    # From the docs: The fourth keyword argument is extra which can be used to pass a dictionary
    # which is used to populate the __dict__ of the LogRecord created for the logging event with user-defined attributes.
    logger.info(
        request.method + " " + request.url.path,
        extra={"extra_info": await get_extra_info(request, response)},
    )


@app.middleware("http")
async def log_request(request: Request, call_next):
    try:
        request.request_body = await request.json()
    except json.decoder.JSONDecodeError:
        request.request_body = None
    response = await call_next(request)
    response.background = BackgroundTask(
        write_log_data, request, response
    )  # https://www.starlette.io/background/
    return response


########################################################################


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    # List the HTML files in the title pages directory
    files = [
        f.name for f in DOWNLOADED_TITLEPAGES_DIR.iterdir() if f.name.endswith(".html")
    ]

    # Render the template with the list of files
    return templates.TemplateResponse(
        "index.html", {"request": request, "files": files}
    )


engine = create_engine(DATABASE_URL, echo=True)


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


class TitleResponse(BaseModel):
    id: Optional[int] = None
    netflix_id: Optional[int] = None
    title: Optional[str] = None
    content_type: Optional[str] = None
    release_year: Optional[int] = None
    runtime: Optional[int] = None
    google_users_rating: Optional[int] = None

    @staticmethod
    def find_google_users_rating(ratings: list[dict]) -> Optional[int]:
        for rating in ratings:
            if rating["vendor"] == "Google users":
                return rating["rating"]


class TitleResponseDecoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, TitleResponse):
            return obj.model_dump()
        return super().default(obj)


@app.get("/api/title/{title_id}", response_model=Dict[int, TitleResponse])
def get_title(title_id: int, session: SessionDep):
    title = session.exec(
        select(
            Title.id,
            Title.netflix_id,
            Title.title,
            Title.content_type,
            Title.release_year,
            Title.runtime,
            Rating.rating.label("google_users_rating"),
        )
        .outerjoin(
            Rating,
            (Rating.netflix_id == Title.netflix_id) & (Rating.vendor == "Google users"),
        )
        .where(Title.netflix_id == title_id)
    ).first()

    if title is None:
        raise HTTPException(status_code=404, detail="Title not found")

    return {title.netflix_id: title}


@app.get("/api/titles", response_model=Dict[int, TitleResponse])
def get_all_available_titles(
    session: SessionDep, available_in: Annotated[list[str] | None, Query()] = ("US",)
):
    titles = session.exec(
        select(
            Title.id,
            Title.netflix_id,
            Title.title,
            Title.content_type,
            Title.release_year,
            Title.runtime,
            # NOTE: included primarily for future reference - didn't really need to aggregate here.
            # I'm really only after the Google rating (see `get_title` above).
            func.jsonb_agg(
                func.jsonb_build_object(
                    "id",
                    Rating.id,
                    "netflix_id",
                    Rating.netflix_id,
                    "vendor",
                    Rating.vendor,
                    "rating",
                    Rating.rating,
                )
            ).label("ratings"),
        )
        .join(Availability)
        .join(Rating)
        .where(Availability.available)
        .where(Availability.country.in_(available_in))
        .group_by(
            Title.id,
            Title.netflix_id,
            Title.title,
            Title.content_type,
            Title.release_year,
            Title.runtime,
        )
    ).all()

    if titles is None:
        raise HTTPException(status_code=404, detail="No titles not found")

    response_obj = {}
    for title in titles:
        title_response = TitleResponse(
            id=title.id,
            netflix_id=title.netflix_id,
            title=title.title,
            content_type=title.content_type,
            release_year=title.release_year,
            runtime=title.runtime,
            google_users_rating=TitleResponse.find_google_users_rating(title.ratings),
        )
        response_obj[title.netflix_id] = title_response

    return response_obj


@app.post("/api/titles")
async def store_title_ids_for_processing(payload: list[int]):
    job_id = str(uuid4())
    global_job_store[job_id] = payload
    return {
        "job_id": job_id,
        "payload_sent": payload,
        "actual_payload_to_submit": global_job_store[job_id],
    }


def find_all_script_elements(html: HTMLContent):
    """
    Finds and returns all <script> elements in the provided HTML string.

    :param html: A string containing the HTML content.
    :return: A list of dictionaries with script details (content and attributes).
    """
    soup = BeautifulSoup(html, "html.parser")
    script_elements = soup.find_all("script")

    scripts_info = []
    for script in script_elements:
        script_info = {
            "content": script.string,  # Inline script content (None if external)
            "attributes": script.attrs,  # Script element attributes (e.g., src, type)
        }
        scripts_info.append(script_info)

    return scripts_info


def _sanitize_pythonmonkey_obj(obj):
    if isinstance(obj, dict):
        return {k: _sanitize_pythonmonkey_obj(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_sanitize_pythonmonkey_obj(v) for v in obj]
    elif obj == pm.null:
        return None
    else:
        if isinstance(obj, float):
            if obj.is_integer():
                return int(obj)
        return obj


async def fetch_and_process_title(
    title_id: int, session_handler: SessionHandler, background_tasks: BackgroundTasks
) -> list[dict]:
    request_url = f"https://www.netflix.com/title/{title_id}"
    async with session_handler.limiter:
        async with session_handler.noauth_session.get(request_url) as response:
            logger.info(f"Starting request for {request_url}")
            if response.status not in (200, 301, 302, 404):
                response.raise_for_status()

            html_content = HTMLContent(await response.text())
            scripts = find_all_script_elements(html_content)

            background_tasks.add_task(
                save_response_body,
                html_content,
                f"/Users/asibalo/Documents/Dev/PetProjects/netflix_critic_data/data/raw/title/{title_id}.html",
            )

            for script in scripts:
                content = script["content"]
                if content is None:
                    continue
                context_def = content.find("reactContext =")
                if context_def != -1:
                    try:
                        react_context = script["content"][context_def:]
                        return _sanitize_pythonmonkey_obj(
                            pm.eval(react_context).models.nmTitleUI.data.sectionData
                        )
                    except (KeyError, AttributeError, pm.SpiderMonkeyError) as e:
                        logger.exception(e)
                        return []


async def scrape_serp_for_ratings(
    netflix_id,
    title_data,
    background_tasks: BackgroundTasks,
) -> list[dict]:
    async with APIFY_SEMAPHORE:
        logger.info(f"Creating APIfy task for {netflix_id}")
        if not title_data:
            return []
        html_content = await get_serp_html(
            netflix_id,
            get_field(title_data, "title"),
            get_field(title_data, "content_type"),
            get_field(title_data, "release_year"),
        )
        background_tasks.add_task(
            save_response_body,
            html_content,
            f"/Users/asibalo/Documents/Dev/PetProjects/netflix_critic_data/data/raw/serp/{netflix_id}.html",
        )
        return await get_ratings(netflix_id, html_content)


async def download_title_and_lookup_ratings(
    title_id,
    http_session_handler: SessionHandler,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    title_data = await fetch_and_process_title(
        title_id,
        http_session_handler,
        background_tasks,
    )
    return {
        "netflix_id": title_id,
        "react_context": title_data,
        "ratings": await scrape_serp_for_ratings(
            title_id, title_data, background_tasks
        ),
    }


async def stream_ratings(job_id: str, db_session, background_tasks: BackgroundTasks):
    tasks = []
    http_session_handler = SessionHandler()

    for title_id in global_job_store[job_id]:
        task = asyncio.create_task(
            download_title_and_lookup_ratings(
                title_id, http_session_handler, background_tasks
            ),
            name=title_id,
        )
        task.add_done_callback(
            lambda t: logger.info(f"Finished task for {t.get_name()}")
        )
        tasks.append(task)

    try:
        titles = []
        availability = []
        ratings = defaultdict(list)

        # TODO it may be prudent to yield a ': keep-alive' message every so often
        for completed_coro in asyncio.as_completed(tasks):
            result = await completed_coro

            netflix_id = result["netflix_id"]
            title_data = result["react_context"]

            title = Title(
                netflix_id=netflix_id,
                title=get_field(title_data, "title"),
                content_type=get_field(title_data, "content_type"),
                release_year=get_field(title_data, "release_year"),
                runtime=get_field(title_data, "runtime"),
                meta_data=title_data,
            )
            titles.append(title)

            availability.append(
                Availability(
                    netflix_id=netflix_id,
                    country="US",
                    titlepage_reachable=True,
                    available=True,
                )
            )

            for rating in result["ratings"]:
                ratings[netflix_id].append(
                    Rating(
                        netflix_id=netflix_id,
                        vendor=rating["vendor"],
                        url=rating["url"],
                        rating=rating["rating"],
                        ratings_count=rating["ratings_count"],
                    )
                )

            title_response = TitleResponse(
                **title.model_dump(),
                google_users_rating=TitleResponse.find_google_users_rating(
                    result["ratings"]
                ),
            )
            msg = json.dumps(
                {title.netflix_id: title_response},
                separators=(",", ":"),
                cls=TitleResponseDecoder,
            )

            yield (
                f"data: {msg}" + "\n\n"
            )  # https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events#event_stream_format

    finally:
        await http_session_handler.close()

        db_session.exec(Title.bulk_insert_ignore_conflicts(titles))
        db_session.exec(Availability.bulk_insert_ignore_conflicts(availability))
        db_session.exec(
            Rating.bulk_insert_ignore_conflicts(itertools.chain(*ratings.values()))
        )
        db_session.commit()


@app.get("/api/stream/{job_id}", response_model=Dict[int, TitleResponse])
async def stream_data(
    job_id: str, db_session: SessionDep, background_tasks: BackgroundTasks
):
    return StreamingResponse(
        stream_ratings(job_id, db_session, background_tasks),
        media_type="text/event-stream",
    )
