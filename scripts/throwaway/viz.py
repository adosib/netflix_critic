"""
This neat little script visualizes requests made to the local uvicorn webserver :)
It was useful for validating a request rate limiting implementation as well as
checking the number of requests/second aiohttp was capable of making.
Have a look at the assets/ dir for the visual.
Mostly copy-pasted from ChatGPT.
"""

import json
import datetime
from pathlib import Path
from collections import defaultdict

import pandas as pd
import matplotlib.pyplot as plt

THIS_DIR = Path(__file__).parent
ROOT_DIR, *_ = [
    parent for parent in THIS_DIR.parents if parent.stem == "netflix_critic"
]


def filter_for_time_range(data: list, seconds=60):
    last_observation = max(data, key=lambda x: x[0])
    timestamp, user_agent = last_observation
    threshold_timestamp = timestamp - datetime.timedelta(seconds=seconds)
    return [item for item in data if item[0] > threshold_timestamp]


if __name__ == "__main__":
    with open(ROOT_DIR / "logs" / "app.log", "r") as f:
        logs = f.read()

    logs = logs.replace("}\n}\n{\n", "}\n},\n{\n")  # add trailing comma
    logs = "[" + logs + "]"  # convert to JSON array
    json_logs = json.loads(logs)

    data = []
    for log_entry in json_logs:
        timestamp_str = log_entry["time"].split(",")[
            0
        ]  # Extract timestamp up to the second (ignore milliseconds)
        user_agent = log_entry["req"]["headers"]["user-agent"]
        timestamp = datetime.datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
        data.append((timestamp, user_agent))

    data = filter_for_time_range(data)

    df = pd.DataFrame(data, columns=["timestamp", "user_agent"])
    df["timestamp"] = df["timestamp"].dt.strftime("%H:%M:%S")  # Round to the second
    grouped = (
        df.groupby(["timestamp", "user_agent"]).size().reset_index(name="request_count")
    )
    pivot_df = grouped.pivot_table(
        index="timestamp",
        columns="user_agent",
        values="request_count",
        aggfunc="sum",
        fill_value=0,
    )

    plt.figure(figsize=(10, 6))
    for user_agent in pivot_df.columns:
        plt.plot(pivot_df.index, pivot_df[user_agent], label=user_agent)

    plt.xlabel("Timestamp (HH:MM:SS)")
    plt.ylabel("Request Count")
    plt.title("Request Count by User-Agent over Time")
    plt.xticks(rotation=45)
    plt.legend(title="User-Agent")
    plt.tight_layout()
    plt.show()
