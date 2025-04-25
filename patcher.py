import argparse
import json
import logging
import sys
import time

import pandas as pd
import requests
import yaml
from tqdm import tqdm

# --- CLI argument parsing ---
parser = argparse.ArgumentParser(
    description="Patch custom fields for use cases via Credo AI API."
)
parser.add_argument(
    "config_path",
    nargs="?",
    default="config.yaml",
    help="Path to the YAML config file (default: config.yaml)",
)
parser.add_argument(
    "--dry-run",
    action="store_true",
    help="If set, only log intended API calls without sending them.",
)
args = parser.parse_args()

CONFIG_PATH = args.config_path
DRY_RUN = args.dry_run

# --- Load config ---
try:
    with open(CONFIG_PATH, "r") as fin:
        config = yaml.safe_load(fin)
except FileNotFoundError:
    logging.error(f"Config file `{CONFIG_PATH}` not found.")
    sys.exit(1)

# --- Perform basic input validation ---
CSV_PATH = config.get("csv_path")
AUTH_TOKEN = config.get("auth_token")
TENANT = config.get("tenant")
FIELDS = config.get("fields")

missing = []
if not CSV_PATH:
    missing.append("csv_path")
if not AUTH_TOKEN:
    missing.append("auth_token")
if not TENANT:
    missing.append("tenant")
if not FIELDS:
    missing.append("fields")
elif not isinstance(FIELDS, list) or not all(isinstance(fld, str) for fld in FIELDS):
    logging.error("The `fields` key must be a list of strings in the config file.")
    sys.exit(1)

if missing:
    logging.error(f"Missing required configuration key(s): {', '.join(missing)}")
    sys.exit(1)


# --- Logging setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# --- Read, clean, and validate CSV ---
try:
    df = pd.read_csv(CSV_PATH).fillna("").rename(columns={"id": "use_case_id"})
    required_columns = {"use_case_id", *FIELDS}
    missing = required_columns - set(df.columns)
    if missing:
        raise ValueError(f"Missing required column(s): {', '.join(missing)}")
except Exception as e:
    logging.error(f"Error processing CSV file '{CSV_PATH}': {e}")
    sys.exit(1)

# --- Headers for API call ---
headers = {"Authorization": f"Bearer {AUTH_TOKEN}", "Content-Type": "application/json"}

# --- Loop over each use case (row) ---
for row_idx, row in tqdm(
    df.iterrows(), total=len(df), desc="Patching use cases", unit="use_case"
):
    use_case_id = row["use_case_id"]

    for field_name in FIELDS:
        field_value = row[field_name]

        url = f"https://api.credo.ai/api/v2/{TENANT}/use_cases/{use_case_id}/custom_fields"

        payload = {
            "data": {
                "type": "use_case_custom_fields",
                "attributes": {"custom_field_id": field_name, "value": field_value},
            }
        }

        if DRY_RUN:
            logging.info(
                f"[DRY RUN] [Row {row_idx}] Would PATCH to: {url}\n"
                f"Field: {field_name} | Value: {field_value}\n"
                f"Payload:\n{json.dumps(payload, indent=2)}\n"
            )
            continue

        try:
            response = requests.patch(url, headers=headers, json=payload)
            if response.ok:  # `ok` is bool for status less than 400, NOT == 200.
                logging.info(
                    f"[Row {row_idx}] PATCH success | use_case_id={use_case_id}, field={field_name}"
                )
            else:
                logging.warning(
                    f"[Row {row_idx}] PATCH failed ({response.status_code}) | {response.text}"
                )
        except Exception as e:
            logging.error(
                f"[Row {row_idx}] PATCH error for use_case_id={use_case_id}, field={field_name}: {e}"
            )

        time.sleep(0.5)  # Wait a bit between requests to avoid timeout.
