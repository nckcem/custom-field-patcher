import logging
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests
from tqdm import tqdm


class TqdmLoggingHandler(logging.Handler):
    """Log handler to interface with `tqdm` without cluttering the terminal.

    This logging handler redirects log messages through `tqdm.write()` to avoid
    breaking progress bars when logging during iterations. This ensures that log output
    and tqdm progress display cleanly together.
    """

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record via `tqdm.write()`.

        Args:
            record (logging.LogRecord): The log record to output.
        """
        try:
            msg = self.format(record)
            tqdm.write(msg)
            self.flush()
        except Exception:
            self.handleError(record)


def fatal_error(message: str) -> None:
    """Log a fatal error message before exiting.

    Args:
        message (str): A message describing the fatal error.
    """
    logging.error(message)
    sys.exit(1)


def get_bearer_token(base_url: str, api_token: str, tenant: str) -> str:
    """Exchange an API token for a Bearer token using the Credo AI auth endpoint.

    Args:
        base_url (str): The base URL of the Credo AI API.
        api_token (str): The API token to exchange.
        tenant (str): The tenant identifier for the API.

    Returns:
        str: The Bearer token.

    Raises:
        SystemExit: If the exchange fails or an error occurs.
    """
    url = f"{base_url}/auth/exchange"
    payload = {"api_token": api_token, "tenant": tenant}

    try:
        response = requests.post(url, json=payload)
        if not response.ok:
            fatal_error(
                f"Failed to exchange API token for Bearer token ({response.status_code})"
            )

        bearer_token = response.json().get("access_token")
        if not bearer_token:
            fatal_error("Bearer token missing from API response.")

        logging.info("Successfully exchanged API token for Bearer token.")
        return bearer_token

    except Exception as e:
        fatal_error(f"Error exchanging API token for Bearer token: {e}")


def get_custom_field_ids(
    base_url: str, tenant: str, headers: Dict[str, str], custom_field_names: List[str]
) -> Dict[str, str]:
    """Fetch the custom field IDs for the specified field names from the Credo AI API.

    Args:
        base_url (str): The base URL of the Credo AI API (e.g., https://api.credo.ai).
        tenant (str): The tenant identifier for the API.
        headers (Dict[str, str]): HTTP headers including authorization.
        custom_field_names (List[str]): List of custom field names to find IDs for.

    Returns:
        Dict[str, str]: A mapping of field names to their corresponding custom field
            IDs.

    Raises:
        SystemExit: If the API request fails or if a critical error occurs during
            processing.
    """
    url = f"{base_url}/api/v2/{tenant}/custom_fields"
    try:
        response = requests.get(
            url, headers=headers, params={"filter[target]": "use_case"}
        )
        if not response.ok:
            fatal_error(
                f"Failed to fetch custom fields for tenant {tenant} ({response.status_code})"
            )

        custom_fields_data = response.json()["data"]
        logging.info(
            f"Successfully fetched {len(custom_fields_data)} custom fields for tenant {tenant}."
        )

        # Map field names to their IDs.
        field_id_map = {}
        available_fields = {
            item["attributes"]["name"]: item["id"] for item in custom_fields_data
        }

        for field_name in custom_field_names:
            if field_name in available_fields:
                field_id_map[field_name] = available_fields[field_name]
                logging.info(
                    f"Found custom field ID for '{field_name}': {available_fields[field_name]}"
                )
            else:
                logging.warning(
                    f"Custom field '{field_name}' not found for tenant {tenant}. Skipping."
                )

        logging.info(
            f"Mapped {len(field_id_map)} custom field(s) based on the provided list."
        )
        return field_id_map

    except Exception as e:
        fatal_error(f"Error fetching custom field IDs: {e}")


def read_and_prepare_csv(
    csv_path: str, custom_field_names: List[str], num_ids: Optional[int] = None
) -> pd.DataFrame:
    """Read a CSV, validate required cols, limit rows, and enforce string typing.

    Args:
        csv_path (str): Path to the CSV file.
        custom_field_names (List[str]): List of custom field names expected in the CSV.
        num_ids (Optional[int], optional): If provided, limit the dataframe to the
            first N rows.

    Returns:
        pd.DataFrame: The cleaned and validated DataFrame.

    Raises:
        SystemExit: If the CSV is invalid, missing required columns, or data cannot be
            properly processed.
    """
    try:
        logging.info(f"Reading CSV file: {csv_path}")
        df = pd.read_csv(csv_path).fillna("").rename(columns={"id": "use_case_id"})

        required_columns = {"use_case_id", *custom_field_names}
        missing_columns = required_columns - set(df.columns)
        if missing_columns:
            raise ValueError(
                f"Missing required column(s): {', '.join(missing_columns)}"
            )
        if num_ids:
            df = df.head(num_ids)
            logging.info(f"Limiting to first {num_ids} use case(s) as specified.")

        # Force specified custom fields to be strings.
        for field_name in custom_field_names:
            try:
                df[field_name] = df[field_name].astype(str)
            except Exception as e:
                fatal_error(f"Failed to cast field `{field_name}` to string: {e}")

        return df

    except Exception as e:
        fatal_error(f"Error processing CSV file '{csv_path}': {e}")


def validate_and_expand_config(
    config: Dict[str, Any],
) -> Tuple[str, str, str, str, List[str], Optional[int]]:
    """Validate required configuration keys and expand environment variables if needed.

    Args:
        config (Dict[str, Any]): Parsed YAML configuration dictionary.

    Returns:
        Tuple[str, str, str, str, List[str], Optional[int]]:
            - csv_path (str)
            - base_url (str)
            - api_token (str)
            - tenant (str)
            - custom_field_names (List[str])
            - num_ids (Optional[int])

    Raises:
        SystemExit: If validation fails.
    """
    REQUIRED_KEYS = [
        "csv_path",
        "base_url",
        "api_token",
        "tenant",
        "custom_field_names",
    ]

    # Validate that required keys are present.
    missing_keys = [key for key in REQUIRED_KEYS if not config.get(key)]
    if missing_keys:
        fatal_error(f"Missing required configuration key(s): {', '.join(missing_keys)}")

    csv_path = config.get("csv_path")
    base_url = config.get("base_url")
    api_token = config.get("api_token")
    tenant = config.get("tenant")
    custom_field_names = config.get("custom_field_names")
    num_ids = config.get("num_ids")

    # Expand environment variable if needed.
    if api_token and api_token.startswith("${") and api_token.endswith("}"):
        env_var = api_token[2:-1]
        api_token = os.getenv(env_var)
        if not api_token:
            fatal_error(f"Environment variable {env_var} not set.")

    # Validate types.
    if not isinstance(custom_field_names, list) or not all(
        isinstance(f, str) for f in custom_field_names
    ):
        fatal_error(
            "The `custom_field_names` key must be a list of strings in the config file."
        )
    if num_ids is not None and (not isinstance(num_ids, int) or num_ids < 1):
        fatal_error("`num_ids` must be a positive integer if provided.")

    return csv_path, base_url, api_token, tenant, custom_field_names, num_ids
