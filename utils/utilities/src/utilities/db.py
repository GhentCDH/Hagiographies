import sqlmodel

from .config import DB_STRING

connect_args = {"connect_timeout": 30} if DB_STRING.startswith("postgresql") else {}

engine = sqlmodel.create_engine(DB_STRING, connect_args=connect_args)
