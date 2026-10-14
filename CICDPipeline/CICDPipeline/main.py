"""Entry point for the CICDPipeline wheel."""

import argparse


def main():
    """Main entry point for the CICDPipeline package."""
    parser = argparse.ArgumentParser(description="CICDPipeline")
    parser.add_argument("--catalog", required=False, default="")
    parser.add_argument("--schema", required=False, default="")
    args = parser.parse_args()

    print(f"Running CICDPipeline with catalog={args.catalog}, schema={args.schema}")


if __name__ == "__main__":
    main()
