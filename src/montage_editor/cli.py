import argparse
import json
import logging
from .environment import detect_environment


def main():
    parser = argparse.ArgumentParser(description="Local gaming montage editor")
    parser.add_argument("command", choices=["doctor"])
    parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    print(json.dumps(detect_environment(), indent=2))
