import argparse
import importlib

ACTIONS = {
    "data_classes": ("create_db.data_classes", "create_schema"),
    
}

def run_action(name: str) -> None:
    module_name, attr = ACTIONS.get(name, (name, None))
    module = importlib.import_module(module_name)
    target = getattr(module, attr, None) if attr else getattr(module, "main", None)
    if not callable(target):
        raise SystemExit(f"No runnable entry point found for {name}.")
    target()

def main() -> None:
    parser = argparse.ArgumentParser(description="Project launcher")
    parser.add_argument("action", help="e.g. data_classes")
    args = parser.parse_args()
    run_action(args.action)

if __name__ == "__main__":
    main()
