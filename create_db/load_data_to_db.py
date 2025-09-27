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
        for table_name in load_order:
            model = MODEL_BY_TABLE.get(table_name)
            if not model:
                print(f"no csv for {table_name} or name mismatch")
                continue

            df = dataframes.get(table_name)
            if df is None:
                print(f"you haven't read {table_name} as a pandas dataframe")
                continue

            try:
                session.bulk_insert_mappings(model, df.to_dict(orient="records"))
            except StatementError as exc:
                session.rollback()
                bad_row = exc.params
                raise RuntimeError(
                    f"failed loading {table_name}: {exc.orig}; row={bad_row}"
                ) from exc

        session.commit()
    except SQLAlchemyError:
        session.rollback()
        raise
    finally:
        session.close()
