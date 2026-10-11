"""Operator commands; account credentials are never command-line arguments."""

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(prog="telegram-mcp")
    parser.add_argument("--version", action="version", version="telegram-mcp 0.1.0")
    parser.parse_args()
    parser.print_help()
