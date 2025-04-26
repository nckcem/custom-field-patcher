import argparse
import json
import logging
import time
from datetime import datetime
from pathlib import Path

import requests
import yaml
from dotenv import load_dotenv
from tqdm import tqdm

import utils


def setup_logging() -> None:
    """Configure logging to output both to file and tqdm-friendly console."""
    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{datetime.now():%Y%m%d}-patcher-log.log"
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s: %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(formatter)
    tqdm_handler = utils.TqdmLoggingHandler()
    tqdm_handler.setFormatter(formatter)
    logging.basicConfig(
        level=logging.INFO,
        handlers=[file_handler, tqdm_handler],
    )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the patching script.

    Returns:
        argparse.Namespace: Parsed CLI arguments, including:
            - config_path (str): Path to the YAML config file (default: config.yaml).
            - dry_run (bool): Whether to simulate API calls without sending them.
    """
    parser = argparse.ArgumentParser(
        description="Patch custom fields for use cases via Credo AI API."
    )
    parser.add_argument(
        "config_path",
        nargs="?",  # ? indicates the argument is optional.
        default="config.yaml",
        help="Path to the YAML config file (default: config.yaml)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="If set, only log intended API calls without sending them.",
    )
    return parser.parse_args()


def main() -> None:
    """Execute the main use case metadata patching script."""

    load_dotenv()  # Load env vars from a .env file (if it exists) into `os.environ`.
    setup_logging()  # Set up logging.

    # Parse CLI args.
    args = parse_args()
    CONFIG_PATH = args.config_path
    DRY_RUN = args.dry_run

    # Load the main config.
    try:
        with open(CONFIG_PATH, "r") as fin:
            config = yaml.safe_load(fin)
    except FileNotFoundError:
        utils.fatal_error(f"Config file not found: {CONFIG_PATH}")

    # Validate and expand the config.
    CSV_PATH, BASE_URL, API_TOKEN, TENANT, CUSTOM_FIELD_NAMES, NUM_IDS = (
        utils.validate_and_expand_config(config)
    )

    # Exchange our API token for a Bearer token to use in our request headers.
    bearer_token = (
        "" if DRY_RUN else utils.get_bearer_token(BASE_URL, API_TOKEN, TENANT)
    )
    HEADERS = {
        "Authorization": f"Bearer {bearer_token}",
        "Content-Type": "application/json",
    }

    # Get custom field UUIDs to construct a `field_name: custom_field_id` mapping.
    custom_field_ids = (
        {field_name: field_name for field_name in CUSTOM_FIELD_NAMES}
        if DRY_RUN
        else utils.get_custom_field_ids(BASE_URL, TENANT, HEADERS, CUSTOM_FIELD_NAMES)
    )
    # Ingest and prepare the input data for processing.
    df = utils.read_and_prepare_csv(CSV_PATH, CUSTOM_FIELD_NAMES, NUM_IDS)

    # Loop over each use case (row) and PATCH the appropriate field names.
    for row_idx, row in tqdm(
        df.iterrows(), total=len(df), desc="Patching use cases", unit="use_case"
    ):
        use_case_id = row["use_case_id"]

        for field_name in CUSTOM_FIELD_NAMES:
            custom_field_id = custom_field_ids.get(field_name)
            if not custom_field_id:
                logging.warning(
                    f"Skipping field '{field_name}' for use case {use_case_id} -"
                    " field not found in API response."
                )
                continue

            field_value = row[field_name]
            url = f"{BASE_URL}/api/v2/{TENANT}/use_cases/{use_case_id}/custom_fields"

            payload = {
                "data": {
                    "type": "use_case_custom_fields",
                    "attributes": {
                        "custom_field_id": custom_field_id,
                        "value": field_value,
                    },
                }
            }

            logging.info(
                f"[Row {row_idx + 2}] Preparing PATCH request:"
                f"\nURL: {url}"
                f"\nPayload:\n{json.dumps(payload, indent=2)}"
            )

            if DRY_RUN:
                continue

            try:
                response = requests.patch(url, headers=HEADERS, json=payload)
                if response.ok:
                    logging.info(
                        f"[Row {row_idx + 2}] PATCH success |"
                        f" use_case_id={use_case_id}, field={field_name}"
                    )
                else:
                    logging.warning(
                        f"[Row {row_idx + 2}] PATCH failed ({response.status_code}) |"
                        f" {response.text}"
                    )
            except Exception as e:
                logging.error(
                    f"[Row {row_idx + 2}] PATCH error for use_case_id={use_case_id},"
                    f" field={field_name}: {e}"
                )

            time.sleep(0.5)  # Wait a bit between requests to avoid timeout.


if __name__ == "__main__":
    main()
