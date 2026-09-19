"""Read-only streaming export: python -m app.export --format json|csv."""
import argparse
import csv
import json
import sqlite3
import sys
from pathlib import Path

from .db import Store


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--database', default='/data/homemind-air.sqlite3')
    p.add_argument('--format', choices=['json', 'csv'], default='json')
    p.add_argument('--since'); p.add_argument('--until'); p.add_argument('--session-id')
    args = p.parse_args()
    store = Store.__new__(Store)
    store.db = sqlite3.connect(Path(args.database).resolve().as_uri() + '?mode=ro', uri=True)
    writer = None
    for row in store.export(args.since, args.until, args.session_id):
        if args.format == 'json':
            print(json.dumps(row, ensure_ascii=False))
        else:
            row = {k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v for k, v in row.items()}
            if writer is None:
                writer = csv.DictWriter(sys.stdout, fieldnames=list(row)); writer.writeheader()
            writer.writerow(row)


if __name__ == '__main__':
    main()
