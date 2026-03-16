import sqlmodel

from .config import DB_STRING

engine = sqlmodel.create_engine(DB_STRING)


def create_updated_at_trigger(engine):
    """Create SQLite triggers to auto-update the updated_at column."""
    with engine.begin() as conn:
        for table_name, table in sqlmodel.SQLModel.metadata.tables.items():
            if "updated_at" in table.columns:
                conn.execute(
                    sqlmodel.text(f"""
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
