import argparse
import json
import logging
import sys
import time
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
AUTH_TOKEN = config.get("auth_token")
TENANT = config.get("tenant")
FIELDS = config.get("fields")
NUM_IDS = config.get("num_ids")

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

# --- Read, clean, and validate CSV ---
try:
    df = pd.read_csv(CSV_PATH).fillna("").rename(columns={"id": "use_case_id"})
    required_columns = {"use_case_id", *FIELDS}
    missing = required_columns - set(df.columns)
    if missing:
        raise ValueError(f"Missing required column(s): {', '.join(missing)}")

    if NUM_IDS:
        df = df.head(NUM_IDS)
        logging.info(f"Limiting to first {NUM_IDS} use case(s) as specified.")

    # Force fields to be strings.
    for field in FIELDS:
        try:
            df[field] = df[field].astype(str)
        except Exception as e:
            logging.error(f"Failed to cast field `{field}` to string: {e}")
            sys.exit(1)

except Exception as e:
    logging.error(f"Error processing CSV file: {CSV_PATH}\n{e}")
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

        url = (
            f"https://api.credo.ai/api/v2/{TENANT}"
            f"/use_cases/{use_case_id}/custom_fields"
        )

        payload = {
            "data": {
                "type": "use_case_custom_fields",
                "attributes": {"custom_field_id": field_name, "value": field_value},
            }
        }

        if DRY_RUN:
            logging.info(
                f"[DRY RUN] [Row {row_idx +  2} in CSV]"
                f"\nWould PATCH to: {url}"
                f"\nField (repr): {repr(field_name)}"
                f"\nValue (repr): {repr(field_value)}"
                f"\nPayload:\n{json.dumps(payload, indent=2)}\n"
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
