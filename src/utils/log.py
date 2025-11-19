import yaml

with open("config.yml") as f:
    cfg = yaml.safe_load(f)

def log(*args):
    if cfg["debug"] == True:
        for arg in args:
            print(f"[debug] {arg}")
