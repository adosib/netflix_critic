import os
import json
import asyncio
import itertools
from http import HTTPStatus
from uuid import uuid4
from typing import Any, Dict, Optional, Annotated
from pathlib import Path
from collections import defaultdict

import aiohttp
import app_logger
from common import (
    JobStore,
    HTMLContent,
    NetflixSessionHandler,
    ContextExtractionError,
    BrightDataSessionHandler,
    get_field,
    get_serp_html,
    configure_logger,
    save_response_body,
    extract_netflix_react_context,
)
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

THIS_DIR = Path(__file__).parent
ROOT_DIR = THIS_DIR.parent
DOWNLOADED_TITLEPAGES_DIR = ROOT_DIR / "data" / "raw" / "title"  # TODO
DOWNLOADED_SERP_PAGES_DIR = ROOT_DIR / "data" / "raw" / "serp"  # TODO

STATUS_REASONS = {x.value: x.name for x in list(HTTPStatus)}

POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", 5432)
POSTGRES_DB = os.getenv("POSTGRES_DB", "postgres")
DATABASE_URL = f"postgresql+psycopg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"


engine = create_engine(DATABASE_URL, echo=True)
global_job_store = JobStore()
app = FastAPI()
app.mount("/title", StaticFiles(directory=DOWNLOADED_TITLEPAGES_DIR, html=True))
templates = Jinja2Templates(directory=THIS_DIR / "templates")

# Add CORS middleware to allow cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_credentials=False,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
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


formatter = app_logger.CustomJSONFormatter("%(asctime)s")
logger = app_logger.get_logger(
    __name__, formatter, fileout=(THIS_DIR / "logs" / f"{Path(__file__).stem}.log")
)
configure_logger(logger)


async def get_extra_info(request: Request, response: Response):
    return {
        "req": {
            "url": request.url.path,
            # request.headers is supposed to be a mapping that handles duplicate keys
            # so coercing to dict is prone to break but ¯\_(ツ)_/¯
            "headers": dict(request.headers),
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
    # From the docs:
    # The fourth keyword argument is extra which can be used to pass a dictionary
    # which is used to populate the __dict__ of the LogRecord
    # created for the logging event with user-defined attributes.
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


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    files = [
        f.name for f in DOWNLOADED_TITLEPAGES_DIR.iterdir() if f.name.endswith(".html")
    ]
    return templates.TemplateResponse(
        "index.html", {"request": request, "files": files}
    )


def get_session():
    with Session(engine) as session:
        yield session


DatabaseSessionDep = Annotated[Session, Depends(get_session)]


class TitlesPostedResponse(BaseModel):
    job_id: str
    payload_sent: list[int]
    actual_payload_to_submit: list[int]


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
def get_title(title_id: int, session: DatabaseSessionDep):
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
    session: DatabaseSessionDep,
    available_in: Annotated[list[str] | None, Query()] = ("US",),
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


@app.post("/api/titles", response_model=TitlesPostedResponse)
async def store_title_ids_for_processing(payload: list[int]):
    job_id = str(uuid4())
    global_job_store[job_id] = payload
    return {
        "job_id": job_id,
        "payload_sent": payload,
        "actual_payload_to_submit": global_job_store[job_id],
    }


async def fetch_and_process_title(
    title_id: int,
    session_handler: NetflixSessionHandler,
    background_tasks: BackgroundTasks,
) -> list[dict]:
    request_path = f"title/{title_id}"
    async with session_handler.limiter:
        try:
            async with session_handler.noauth_session.get(request_path) as response:
                logger.info(f"Starting request for {request_path}")
                if response.status not in (200, 301, 302, 404):
                    response.raise_for_status()

                html_content = HTMLContent(await response.text())

                background_tasks.add_task(
                    save_response_body,
                    html_content,
                    DOWNLOADED_TITLEPAGES_DIR / f"{title_id}.html",
                )

                return extract_netflix_react_context(html_content)

        except (ContextExtractionError, aiohttp.ConnectionTimeoutError) as e:
            logger.exception(e)
            return []


async def scrape_serp_for_ratings(
    netflix_id,
    title_data,
    brd_session_handler: BrightDataSessionHandler,
    background_tasks: BackgroundTasks,
) -> list[dict]:
    async with brd_session_handler.limiter:
        logger.info(f"Attempting to get SERP reviews for {netflix_id}")
        if not title_data:
            return []
        serp_response = await get_serp_html(
            netflix_id,
            get_field(title_data, "title"),
            get_field(title_data, "content_type"),
            get_field(title_data, "release_year"),
            session=brd_session_handler.choose_session(),
        )
        background_tasks.add_task(
            save_response_body,
            serp_response.html,
            DOWNLOADED_SERP_PAGES_DIR / f"{netflix_id}.html",
        )
        return [rating.__dict__ for rating in serp_response.ratings]


async def download_title_and_lookup_ratings(
    title_id,
    nflx_session_handler: NetflixSessionHandler,
    brd_session_handler: BrightDataSessionHandler,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    title_data = await fetch_and_process_title(
        title_id,
        nflx_session_handler,
        background_tasks,
    )
    return {
        "netflix_id": title_id,
        "react_context": title_data,
        "ratings": await scrape_serp_for_ratings(
            title_id, title_data, brd_session_handler, background_tasks
        ),
    }


async def stream_ratings(
    job_id: str, db_session: DatabaseSessionDep, background_tasks: BackgroundTasks
):
    tasks = []
    nflx_session_handler = NetflixSessionHandler()
    brd_session_handler = BrightDataSessionHandler()

    for title_id in global_job_store[job_id]:
        task = asyncio.create_task(
            download_title_and_lookup_ratings(
                title_id, nflx_session_handler, brd_session_handler, background_tasks
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
        await nflx_session_handler.close()
        await brd_session_handler.close()

        db_session.exec(Title.bulk_insert_ignore_conflicts(titles))
        db_session.exec(Availability.bulk_insert_ignore_conflicts(availability))
        db_session.exec(
            Rating.bulk_insert_ignore_conflicts(itertools.chain(*ratings.values()))
        )
        db_session.commit()


@app.get("/api/stream/{job_id}", response_model=Dict[int, TitleResponse])
async def stream_data(
    job_id: str, db_session: DatabaseSessionDep, background_tasks: BackgroundTasks
):
    return StreamingResponse(
        stream_ratings(job_id, db_session, background_tasks),
        media_type="text/event-stream",
    )
