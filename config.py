# config.py
from dataclasses import dataclass
from typing import List
from dotenv import load_dotenv
import os

load_dotenv()

@dataclass
class Config:
    BOT_TOKEN: str
    ADMIN_IDS: List[int]
    DB_HOST: str
    DB_USER: str
    DB_PASSWORD: str
    DB_NAME: str
    DB_PORT: int

def load_config() -> Config:
    return Config(
        BOT_TOKEN=os.getenv("BOT_TOKEN"),
        ADMIN_IDS=list(map(int, os.getenv("ADMIN_IDS").split(","))),
        DB_HOST=os.getenv("DB_HOST"),
        DB_USER=os.getenv("DB_USER"),
        DB_PASSWORD=os.getenv("DB_PASSWORD"),
        DB_NAME=os.getenv("DB_NAME"),
        DB_PORT=int(os.getenv("DB_PORT"))
    )
