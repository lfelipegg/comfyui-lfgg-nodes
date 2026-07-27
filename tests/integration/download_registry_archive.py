import argparse

from tests.integration.harness import download_registry_archive


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("node_id")
    parser.add_argument("version")
    parser.add_argument("destination")
    args = parser.parse_args()
    download_registry_archive(args.node_id, args.version, args.destination)


if __name__ == "__main__":
    main()
