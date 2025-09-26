import os
import pandas as pd


clean_data_path = os.path.join(os.path.dirname(__file__), "..", "data", "data_clean")

dataframes = {}

for file in os.listdir(clean_data_path):
    if file.endswith(".csv"):
        file_path = os.path.join(clean_data_path, file)
        key = os.path.splitext(file)[0]
        dataframes[key] = pd.read_csv(file_path, encoding="latin1")


for key, val in dataframes.items():
    print(key)
    print(val.columns)
