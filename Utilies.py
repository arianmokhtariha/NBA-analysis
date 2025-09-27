import pandas as pd
import importlib
import subprocess
import sys



def make_df_pretty(dataframe:pd.DataFrame):
    for i in dataframe.columns:
        if type(dataframe[i][0]) is list: 
            dataframe[i]=dataframe[i].apply(lambda lst : list(dict.fromkeys(lst)))
            dataframe[i]=dataframe[i].apply(lambda x: ",".join(map(str,x)))
    dataframe=dataframe.replace('' , pd.NA)
 
 
def is_installed(pkg_name):
    try:
        return importlib.util.find_spec(pkg_name) is not None
    except Exception:
        return False
    
def pip_install(packages, upgrade = False, user = False):
    args = [sys.executable, "-m", "pip", "install"]
    if upgrade:
        args.append("--upgrade")
    if user:
        args.append("--user")
    args += list(packages)

    print("Running:", " ".join(args))
    subprocess.check_call(args)
    
def ensure_packages(packages, upgrade = False, user = False):
    missing = []
    for pkg in packages:
        if not is_installed(pkg):
            missing.append(pkg)

    if missing:
        pip_install(missing, upgrade=upgrade, user=user)
    else:
        print("All packages already installed:", ", ".join(packages))
