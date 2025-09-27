import os
import pandas as pd
from create_db.data_classes import Base
from sqlalchemy.exc import SQLAlchemyError, StatementError
from create_db.data_classes import (
    SessionLocal,
    Team,
    Player,
    TeamPerformance,
    PlayerStat,
    MVPWinner,
    SeasonStat,
    MVPCandidate,
)
from sqlalchemy import text

##########################################----

clean_data_path = os.path.join(os.path.dirname(__file__), "..", "data", "data_clean")

##reading all our clean csv files as dataframes and keeping them in a dictionary
dataframes = {}

for file in os.listdir(clean_data_path):
    if file.endswith(".csv"):
        file_path = os.path.join(clean_data_path, file)
        key = os.path.splitext(file)[0]
        dataframes[key] = pd.read_csv(file_path, encoding="latin1")

# for key, val in dataframes.items():
#     print(key)
#     print(val.columns)


def to_records(df: pd.DataFrame) -> list[dict]:
    rows = []
    for row in df.to_dict(orient="records"):
        rows.append({col: (None if pd.isna(val) else val) for col, val in row.items()})
    return rows


MODEL_BY_TABLE = {
    Team.__tablename__: Team,
    Player.__tablename__: Player,
    TeamPerformance.__tablename__: TeamPerformance,
    PlayerStat.__tablename__: PlayerStat,
    MVPWinner.__tablename__: MVPWinner,
    SeasonStat.__tablename__: SeasonStat,
    MVPCandidate.__tablename__: MVPCandidate,
}

load_order = [table.name for table in Base.metadata.sorted_tables]
##order of tables is important when populating a relational database (because of foreign keys)





def populate_db():
    session = SessionLocal()
    try:
        session.execute(text("SET FOREIGN_KEY_CHECKS=0"))

        for table_name in load_order:
            model = MODEL_BY_TABLE.get(table_name)
            if not model:
                print(f"no csv for {table_name} or name mismatch")
                continue

            df = dataframes.get(table_name)
            if df is None:
                print(f"you haven't read {table_name} as a pandas dataframe")
                continue

            records = to_records(df)

            try:
                session.bulk_insert_mappings(model, records)
            except StatementError as exc:
                session.rollback()
                raise RuntimeError(f"failed loading {table_name}: {exc.orig}") from exc

        session.commit()
    except SQLAlchemyError:
        session.rollback()
        raise
    finally:
        try:
            session.execute(text("SET FOREIGN_KEY_CHECKS=1"))
            session.commit()
        finally:
            session.close()
