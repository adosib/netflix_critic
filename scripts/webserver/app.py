import sys
import json
import logging
from http import HTTPStatus
from typing import Dict, Annotated
from pathlib import Path

import uvicorn
from models import Title, Availability
from fastapi import Query, Depends, FastAPI, Request, Response, HTTPException
from sqlmodel import Session, select, create_engine
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask
from starlette.middleware.cors import CORSMiddleware

THIS_DIR = Path(__file__).parent
ROOT_DIR, *_ = [
    parent for parent in THIS_DIR.parents if parent.stem == "netflix_critic"
]
DOWNLOADED_TITLEPAGES_DIR = ROOT_DIR / "data" / "raw" / "title"
DATABASE_URL = "postgresql://localhost:5432/postgres"
STATUS_REASONS = {x.value: x.name for x in list(HTTPStatus)}

app = FastAPI()
app.mount("/title", StaticFiles(directory=DOWNLOADED_TITLEPAGES_DIR, html=True))

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


def get_extra_info(request: Request, response: Response):
    return {
        "req": {
            "url": request.url.path,
            "headers": dict(
                request.headers
            ),  # request.headers is supposed to be a mapping that handles duplicate keys so coercing to dict is prone to break but ¯\_(ツ)_/¯
            "method": request.method,
            "http_version": request.scope["http_version"],
            "original_url": request.url.path,
            "query": {},
        },
        "res": {
            "status_code": response.status_code,
            "status": STATUS_REASONS.get(response.status_code),
            "headers": dict(response.headers),
        },
    }


def write_log_data(request, response):
    # From the docs: The fourth keyword argument is extra which can be used to pass a dictionary
    # which is used to populate the __dict__ of the LogRecord created for the logging event with user-defined attributes.
    logger.info(
        request.method + " " + request.url.path,
        extra={"extra_info": get_extra_info(request, response)},
    )


@app.middleware("http")
async def log_request(request: Request, call_next):
    response = await call_next(request)
    response.background = BackgroundTask(
        write_log_data, request, response
    )  # https://www.starlette.io/background/
    return response


########################################################################


@app.get("/", response_class=HTMLResponse)
def read_root():
    files = []
    for filepath in DOWNLOADED_TITLEPAGES_DIR.iterdir():
        filename = filepath.name
        if not filename.endswith(".html"):
            continue
        filename = f'<li><a href="/title/{filename}">{filename}</a></li>'
        files.append(filename)

    style = """body {
                    font-family: Arial, sans-serif;
                    background-color: #f4f4f4;
                    margin: 0;
                    padding: 0;
                }
                .container {
                    max-width: 800px;
                    margin: 20px auto;
                    padding: 20px;
                    background-color: #fff;
                    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
                    border-radius: 8px;
                }
                h1 {
                    font-size: 2rem;
                    margin-bottom: 20px;
                }
                ul {
                    list-style-type: none;
                    padding: 0;
                }
                li {
                    margin: 10px 0;
                }
                a {
                    text-decoration: none;
                    color: #007BFF;
                    font-size: 1.1rem;
                }
                a:hover {
                    color: #0056b3;
                    text-decoration: underline;
                }
                .footer {
                    text-align: center;
                    font-size: 0.8rem;
                    margin-top: 30px;
                    color: #888;
                }"""

    return f"""
    <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>File Directory</title>
            <style>
                {style}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>File Directory</h1>
                <p> There are {len(files)} titles to choose from! </p>
                <ul>
                    { "\n".join(files) }
                </ul>
            </div>
            <div class="footer">
                <p>&copy; Shkr8up ChatGPT Generated</p>
            </div>
        </body>
        </html>
    """


engine = create_engine(DATABASE_URL, echo=True)


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


@app.get("/api/title/{title_id}", response_model=Title)
def get_title_data(title_id: int, session: SessionDep):
    title = session.exec(select(Title).where(Title.netflix_id == title_id)).first()
    if title is None:
        raise HTTPException(status_code=404, detail="Title not found")
    return title


@app.get("/api/titles", response_model=Dict[int, Title])
def get_all_titles(
    session: SessionDep, available_in: Annotated[list[str] | None, Query()] = ("US",)
):
    titles = session.exec(
        select(Title)
        .join(Availability)
        .where(Availability.available)
        .where(Availability.country.in_(available_in))
    ).all()
    if titles is None:
        raise HTTPException(status_code=404, detail="No titles not found")
    titles_dict = {title.netflix_id: title for title in titles}
    return titles_dict


if __name__ == "__main__":
    uvicorn.run(app, log_level="info")
