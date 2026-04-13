import sqlmodel
from sqlalchemy import event, text

from .config import DB_STRING

if DB_STRING.startswith("sqlite"):
    connect_args = {"timeout": 30}
elif DB_STRING.startswith("postgresql"):
    connect_args = {"connect_timeout": 30}
else:
    connect_args = {}

engine = sqlmodel.create_engine(DB_STRING, connect_args=connect_args)

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if engine.dialect.name == "sqlite":
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


def create_updated_at_trigger(engine):
    """Create SQLite/Postgres triggers to auto-update the updated_at column."""
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(
                text("""
                CREATE OR REPLACE FUNCTION update_updated_at_column()
                RETURNS TRIGGER AS $$
                BEGIN
                    NEW.updated_at = NOW();
                    RETURN NEW;
                END;
                $$ language 'plpgsql';
                """)
            )
            
        for table_name, table in sqlmodel.SQLModel.metadata.tables.items():
            if "updated_at" in table.columns:
                if engine.dialect.name == "sqlite":
                    conn.execute(
                        text(f"""
                        CREATE TRIGGER IF NOT EXISTS update_{table_name}_modtime
                            AFTER UPDATE ON {table_name}
                            FOR EACH ROW
                        BEGIN
                            UPDATE {table_name}
                            SET updated_at = CURRENT_TIMESTAMP
                            WHERE id = NEW.id;
                        END;
                        """)
                    )
                elif engine.dialect.name == "postgresql":
                    conn.execute(
                        text(f"""
                        DROP TRIGGER IF EXISTS update_{table_name}_modtime ON {table_name};
                        CREATE TRIGGER update_{table_name}_modtime
                            BEFORE UPDATE ON {table_name}
                            FOR EACH ROW
                            EXECUTE FUNCTION update_updated_at_column();
                        """)
                    )
