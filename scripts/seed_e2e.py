"""Create the two real-OJ fixtures and persist an exclusive ownership ledger."""
import argparse
from pathlib import Path
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.e2e_fixtures import seed
from scripts.prepare_e2e import ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT/'config_center/e2e.example.yaml')
    parser.add_argument('--ledger', type=Path, required=True)
    args = parser.parse_args()
    result = seed(args.config, args.ledger)
    print(f"PASS: run {result['run_id']}, {len(result['problems'])} fixtures created and read back")


if __name__ == '__main__':
    main()
