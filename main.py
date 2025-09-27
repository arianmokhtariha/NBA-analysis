import argparse
import importlib

ACTIONS = {
    "create_data_classes": ("create_db.data_classes", "create_schema"),
    "reset_db": ("create_db.data_classes", "reset_schema"),
    "load_data": ("create_db.load_data_to_db", "populate_db"),
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
    parser.add_argument("action", nargs="?", choices=ACTIONS)
    args = parser.parse_args()

    if not args.action:
        args.action = input(f"Choose action {list(ACTIONS)}: ").strip()

    run_action(args.action)


if __name__ == "__main__":
    main()
