import sqlmodel
from sqlalchemy import text

from .config import DB_STRING

connect_args = {"connect_timeout": 30} if DB_STRING.startswith("postgresql") else {}

engine = sqlmodel.create_engine(DB_STRING, connect_args=connect_args)


def create_updated_at_trigger(engine):
    """Create Postgres triggers to auto-update the updated_at column."""
    with engine.begin() as conn:
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
                conn.execute(
                    text(f"""
                    DROP TRIGGER IF EXISTS update_{table_name}_modtime ON {table_name};
                    CREATE TRIGGER update_{table_name}_modtime
                        BEFORE UPDATE ON {table_name}
                        FOR EACH ROW
                        EXECUTE FUNCTION update_updated_at_column();
                    """)
                )
