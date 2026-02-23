from sqlalchemy import event
from sqlmodel import Session, create_engine

DATABASE_URL = "sqlite:////data/hagiographies.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA query_only=ON;")   # ← enkel dit, geen WAL
    cursor.close()

def get_session():
    with Session(engine) as session:
        yield session
