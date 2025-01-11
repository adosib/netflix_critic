import sys
import json
import logging
from http import HTTPStatus
from typing import Dict, Optional, Annotated
from pathlib import Path

import uvicorn
from models import Title, Rating, Availability
from fastapi import Query, Depends, FastAPI, Request, Response, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select, create_engine
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask
from starlette.middleware.cors import CORSMiddleware

THIS_DIR = Path(__file__).parent
ROOT_DIR, *_ = [
    parent for parent in THIS_DIR.parents if parent.stem == "netflix_critic"
]
DOWNLOADED_TITLEPAGES_DIR = ROOT_DIR / "netflix_critic_data" / "data" / "raw" / "title"
DATABASE_URL = "postgresql://localhost:5432/postgres"
STATUS_REASONS = {x.value: x.name for x in list(HTTPStatus)}

app = FastAPI()
app.mount("/title", StaticFiles(directory=DOWNLOADED_TITLEPAGES_DIR, html=True))
templates = Jinja2Templates(directory=THIS_DIR / "templates")

# Add CORS middleware to allow cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Or more restricted origins like "https://www.netflix.com"
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods (GET, POST, etc.)
    allow_headers=["*"],  # Allow all headers
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
    id: int
    netflix_id: int
    title: Optional[str]
    content_type: Optional[str]
    release_year: Optional[int]
    runtime: Optional[int]
    rating: Optional[int]


@app.get("/api/title/{title_id}", response_model=Title)
def get_title_data(title_id: int, session: SessionDep):
    title = session.exec(select(Title).where(Title.netflix_id == title_id)).first()
    if title is None:
        raise HTTPException(status_code=404, detail="Title not found")
    return title


@app.get("/api/titles", response_model=Dict[int, TitleResponse])
def get_all_titles(
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
            Rating.rating,
        )
        .join(Availability)
        .join(
            Rating,
            (Rating.netflix_id == Title.netflix_id) & (Rating.vendor == "Google users"),
            isouter=True,
        )
        .where(Availability.available)
        .where(Availability.country.in_(available_in))
    ).all()
    if titles is None:
        raise HTTPException(status_code=404, detail="No titles not found")
    titles_dict = {title.netflix_id: title for title in titles}
    return titles_dict


@app.post("/api/titles", response_model=Dict[int, TitleResponse])
def post_titles(payload: list[int]):
    return {
        netflix_id: TitleResponse(
            id=123,
            netflix_id=netflix_id,
            title="dummy",
            content_type="movie",
            release_year=2025,
            runtime=9999,
            rating=88,
        )
        for netflix_id in payload
    }


if __name__ == "__main__":
    uvicorn.run(app, log_level="info")
