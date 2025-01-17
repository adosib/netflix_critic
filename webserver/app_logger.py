# Shoutout: https://stackoverflow.com/questions/70891687/how-do-i-get-my-fastapi-applications-console-log-in-json-format-with-a-differen/70899261#70899261
import sys
import json
import logging


class CustomJSONFormatter(logging.Formatter):
    def __init__(self, fmt):
        super().__init__(fmt)

    def format(self, record):
        super().format(record)
        return json.dumps(self.get_log(record), indent=2)

    def get_log(self, record):
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


def get_file_handler(formatter, filename):
    file_handler = logging.handlers.RotatingFileHandler(filename)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    return file_handler


def get_stream_handler(formatter):
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(logging.DEBUG)
    stream_handler.setFormatter(formatter)
    return stream_handler


def get_logger(name, formatter, fileout=None):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.addHandler(get_stream_handler(formatter))
    if fileout:
        logger.addHandler(get_file_handler(formatter, fileout))
    return logger
