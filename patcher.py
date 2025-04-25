import argparse
import json
import logging
import sys
import time
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
import yaml
from tqdm import tqdm

# --- Custom TQDM-Compatible Logger ---
class TqdmLoggingHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            tqdm.write(msg)
            self.flush()
        except Exception:
            self.handleError(record)

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
    logging.error(f"Config file not found: {CONFIG_PATH}")
    sys.exit(1)

# --- Perform basic input validation ---
CSV_PATH = config.get("csv_path")
API_URL = config.get("api_url")
AUTH_TOKEN = config.get("auth_token")
# Expand environment variables in auth token
if AUTH_TOKEN and AUTH_TOKEN.startswith("${") and AUTH_TOKEN.endswith("}"):
    env_var = AUTH_TOKEN[2:-1]
    AUTH_TOKEN = os.getenv(env_var)
    if not AUTH_TOKEN:
        logging.error(f"Environment variable {env_var} not set")
        sys.exit(1)
TENANT = config.get("tenant")
CUSTOM_FIELD_NAMES = config.get("custom_field_names")
NUM_IDS = config.get("num_ids")

missing = []
if not CSV_PATH:
    missing.append("csv_path")
if not API_URL:
    missing.append("api_url")
if not AUTH_TOKEN:
    missing.append("auth_token")
if not TENANT:
    missing.append("tenant")
if not CUSTOM_FIELD_NAMES:
    missing.append("custom_field_names")
elif not isinstance(CUSTOM_FIELD_NAMES, list) or not all(isinstance(fld, str) for fld in CUSTOM_FIELD_NAMES):
    logging.error("The `custom_field_names` key must be a list of strings in the config file.")
    sys.exit(1)

if missing:
    logging.error(f"Missing required configuration key(s): {', '.join(missing)}")
    sys.exit(1)

if NUM_IDS is not None and (not isinstance(NUM_IDS, int) or NUM_IDS < 1):
    logging.error("`num_ids` must be a positive integer if provided.")
    sys.exit(1)


# --- Setup logging ---
log_dir = Path("logs")
log_dir.mkdir(parents=True, exist_ok=True)

log_file = log_dir / f"{datetime.now():%Y%m%d}-patcher-log.log"

formatter = logging.Formatter(
    "%(asctime)s | %(levelname)s: %(message)s", "%Y-%m-%d %H:%M:%S"
)

file_handler = logging.FileHandler(log_file)
file_handler.setFormatter(formatter)

tqdm_handler = TqdmLoggingHandler()
tqdm_handler.setFormatter(formatter)

logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, tqdm_handler],
)

custom_field_ids = {}

try:    
    # --- Headers for API call ---
    headers = {"Authorization": f"Bearer {AUTH_TOKEN}", "Content-Type": "application/json"}

    try:
        response = requests.get(f"{API_URL}/{TENANT}/custom_fields", headers=headers, params={"filter[target]": "use_case"})
        if response.ok:  # `ok` is bool for status less than 400, NOT == 200.
            logging.info(
                f"Successfully fetched custom fields for tenant {TENANT}."
            )

            # --- Get custom fields (of type "use_case") for tenant ---
            custom_fields_json_data = response.json()["data"]
            logging.info(f"Found {len(custom_fields_json_data)} custom fields for tenant {TENANT}.")

            # for each field name in CUSTOM_FIELD_NAMES, find the corresponding custom field id and save it in a map
            for field_name in CUSTOM_FIELD_NAMES:
                field_found = False
                for item in custom_fields_json_data:
                    if item["attributes"]["name"] == field_name:
                        custom_field_ids[field_name] = item["id"]
                        logging.info(f"Found custom field ID for {field_name}: {item['id']}")
                        field_found = True
                        break
                if not field_found:
                    logging.warning(f"Custom field '{field_name}' not found for tenant {TENANT}. This field will be skipped.")

            logging.info(f"Found {len(custom_field_ids)} custom field IDs for tenant {TENANT} based on the CUSTOM_FIELD_NAMES list.")
        else:
            logging.warning(
                f"Failed to fetch custom fields for tenant {TENANT} ({response.status_code}) | {response.text}"
            )
    except Exception as e:
        logging.error(
            f"Error getting custom field IDs: {e}"
        )
except Exception as e:
    logging.error(f"Error getting custom field IDs: {e}")
    sys.exit(1)

# --- Read, clean, and validate CSV ---
try:
    logging.info(f"Reading CSV file: {CSV_PATH}")
    df = pd.read_csv(CSV_PATH).fillna("").rename(columns={"id": "use_case_id"})
    required_columns = {"use_case_id", *CUSTOM_FIELD_NAMES}
    missing = required_columns - set(df.columns)
    if missing:
        raise ValueError(f"Missing required column(s): {', '.join(missing)}")

    if NUM_IDS:
        df = df.head(NUM_IDS)
        logging.info(f"Limiting to first {NUM_IDS} use case(s) as specified.")

    # Force field names to be strings.
    for field_name in CUSTOM_FIELD_NAMES:
        try:
            df[field_name] = df[field_name].astype(str)
        except Exception as e:
            logging.error(f"Failed to cast field `{field_name}` to string: {e}")
            sys.exit(1)

except Exception as e:
    logging.error(f"Error processing CSV file: {CSV_PATH}\n{e}")
    sys.exit(1)

# --- Loop over each use case (row) ---
for row_idx, row in tqdm(
    df.iterrows(), total=len(df), desc="Patching use cases", unit="use_case"
):
    use_case_id = row["use_case_id"]

    for field_name in CUSTOM_FIELD_NAMES:
        # Skip if field wasn't found in the API response
        if field_name not in custom_field_ids:
            logging.warning(f"Skipping field '{field_name}' for use case {use_case_id} - field not found in API response")
            continue
            
        field_value = row[field_name]
        custom_field_id = custom_field_ids[field_name]
        url = f"{API_URL}/{TENANT}/use_cases/{use_case_id}/custom_fields"

        payload = {
            "data": {
                "type": "use_case_custom_fields",
                "attributes": {"custom_field_id": custom_field_id, "value": field_value},
            }
        }

        logging.info(
            f"[Row {row_idx + 2} in CSV]"
            f"\nWill PATCH to: {url}"
            f"\nPayload:\n{json.dumps(payload, indent=2)}\n"
        )

        if not DRY_RUN:
            try:
                response = requests.patch(url, headers=headers, json=payload)
                if response.ok:  # `ok` is bool for status less than 400, NOT == 200.
                    logging.info(
                        f"[Row {row_idx + 2}] PATCH success | use_case_id={use_case_id}, field={field_name}"
                    )
                else:
                    logging.warning(
                        f"[Row {row_idx + 2}] PATCH failed ({response.status_code}) | {response.text}"
                    )
            except Exception as e:
                logging.error(
                    f"[Row {row_idx + 2}] PATCH error for use_case_id={use_case_id}, field={field_name}: {e}"
                )

            time.sleep(0.5)  # Wait a bit between requests to avoid timeout.
