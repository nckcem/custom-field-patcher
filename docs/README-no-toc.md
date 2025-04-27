<!-- omit in toc -->
# Credo AI Use Case Custom Field Patcher

Given a ***list of custom field names***, this utility ***updates their values*** for ***corresponding use cases*** in the Credo AI platform. It operates in 3 phases:
  1. Read mapping data from an ***input CSV file***.
  2. ***Map field-value pairs*** to their corresponding use cases.
  3. ***Submit PATCH requests*** to update custom field values for specified use cases through the Credo AI API.

---
<!-- omit in toc -->
## 🗂️ Table of Contents
[TOC]

---

## 1. Overview 🗺️

For each use case (row) in the provided CSV:
- The script identifies the use case by its value under the `id` column.
- For each field specified in the configuration, it:
  - Extracts the corresponding value from the CSV row.
  - ***Casts that value as a string***.
  - Sends a PATCH request(s) to update the custom field(s) for that specific use case.

This allows for batch updating multiple custom fields across many use cases in an automated and reliable manner. For example, if each use case had 3 custom fields to update, the script would update `field_1`, `field_2`, and `field_3` on `use_case_1` before moving to `use_case_2`.

### 1.1 Key Characteristics — *Please Review* 🎯

> ***These key characteristics describe how the script operates and what to expect during execution. Please review them carefully before running the script.***

1. **Field Validation**: Ensures *all* fields listed in the config exist in the CSV.
2. **Progress Tracking**: Displays a dynamic progress bar for real-time feedback.
3. **Error Handling**: Logs clear errors (to `./logs`) for config, CSV, and API issues.
4. **Request Throttling**: Waits `0.5` seconds between API calls to avoid server overload.
5. ⚠️ **String Enforcement**: Casts all field values to strings; blank values become empty strings.
6. ⚠️ **Consistent Overwrites**: Sends all values (including blanks) in PATCH requests to guarantee updates.

---

## 2. Quickstart ⚡
1. Install `Python 3.13.2`.
2. Install Git Bash (Windows only). On macOS/Linux, use the native terminal.
3. Open an IDE (e.g., VS Code).
4. Clone this repository.
5. Set up a virtual environment.
   1. Ensure `virtualenv` is installed: `pip install virtualenv`
   2. Create a virtual environment: `virtualenv venv --python=python3.13.2`
   3. Activate the newly-created virtual environment:
      1. On macOS/Linux: `venv/bin/activate`
      2. On Windows (Git Bash or PowerShell): `source venv/Scripts/activate`
   4. Install dependencies: `pip install -r requirements.txt`
   5. Adjust the `config.yaml` to your current needs.
   6. Run in dry-run mode: `python patcher.py config.yaml --dry-run`


---

## 3. Requirements 🧰

- Python `3.13.2`
- Install required packages with:
  ```bash
  pip install -r requirements.txt
  ```
- See [requirements.txt](requirements.txt) for specifics.

---

## 4. Configuration ⚙️

Create a `config.yaml` file with the following structure:

```yaml
# Path to the CSV file
csv_path: "path/to/your_file.csv"

# Base URL
base_url: "https://api.your-url.com"

# API authentication token (referenced from an ENV file)
api_token: "${CREDO_AI_API_TOKEN}"

# Tenant identifier for the API
tenant: "your_tenant_id_here"

# Number of IDs (rows) to process. Leave empty or null to process all.
num_ids:

# List of custom field names to update
custom_field_names:
  - "Deployment Date"
  - "Business Type"
  - ...
  - "Is a Vendor"
```

---

### 4.1 Config Key Definitions 🗝️

- **`csv_path`** (`str`)
  Path to the input CSV file.

- **`base_url`** (`str`)
  Base URL of the Credo AI API server.

- **`api_token`** (`str`)
  API token used for authentication (referenced via environment variable).

- **`tenant`** (`str`)
  Tenant or workspace identifier used in API endpoints.

- **`num_ids`** (`Optional[int]`)
  Number of use cases to process.
  If omitted (`null`, `~`, or blank), all rows will be processed.
  Rows are processed starting from the first data row (after the header).

- **`custom_field_names`** (`List[str]`)
  List of custom field names to update.
  These field names must exactly match column headers in the input CSV.

---

## 5. CSV Format 🧮

The CSV input file must include:
- An `id` column (which is renamed to `use_case_id` in the code for clarity).
- A column for *each field* specified in `custom_field_names`.

Example:

| id                       | Deployment Date  | Business Type | ...  | Is a Vendor |
|--------------------------|------------------|---------------|------|-------------|
| 2p8KNZ7YShyEqkdSUhinT2   | 2024-12-01       | Research      | ...  | TRUE        |
| Q5bGNjz8HDzAhg4ndE2pum   | 2025-01-15       | Commercial    | ...  | FALSE       |
| ...                      | ...              | ...           | ...  | ...         |
| Q5bGNjz8HDzAhg4ndE2pum   | 2025-02-29       | IOPS          | ...  | TRUE        |

> ***It doesn't matter if the CSV has additional columns beyond those required.***

---

## 6. Authentication 🔒

This script requires an ***API token*** for authentication with the Credo AI API. Instead of hardcoding the token directly into configuration files, the script securely loads it from a local `.env` file.

### 6.1 Setting Up Env Auth 🛡️
1. Create a file named `.env` in the root directory of the project.
2. Inside the `.env` file, add the following line:

    ```bash
    CREDO_AI_AUTH_TOKEN=your_actual_token_here
    ```

   Replace `your_actual_token_here` with your actual API token provided by Credo AI, not encased in double-quotes (e.g., `abc123`, not `"abc123"`).

3. Ensure that your `config.yaml` references this environment variable:

    ```yaml
    api_token: "${CREDO_AI_AUTH_TOKEN}"
    ```

The script will automatically load this environment variable at runtime using `python-dotenv`.
If the token is missing or invalid, the script will exit with an error.

### 6.2 Security Note ⚠️
- ***Never commit your `.env` file*** to version control (e.g., GitHub).
- ***Always ensure your `.gitignore` includes `.env`*** to protect sensitive credentials.

---


## 7. Usage 🖥️

***Run this script in dry-run mode first (i.e. with `--dry-run`).***

In dry-run mode, the script logs the intended PATCH requests, including URLs and payloads, *without* sending them to the server.

### 7.1 Dry-run Mode 🧪

To simulate the API requests ***without making actual changes (for validation/testing)***:
  ```bash
  python patcher.py config.yaml --dry-run
  ```

### 7.2 Basic Run ✅

To run the script and perform ***real PATCH operations***:
  ```bash
  python patcher.py config.yaml
  ```
### 7.3 Default Config 🎛️

***If no config file is provided, the script defaults to using `config.yaml`:***

  ```bash
  python patcher.py --dry-run
  ```

---

## 8. Support 📞

For questions or technical issues, please contact your Credo AI technical representative.

---
