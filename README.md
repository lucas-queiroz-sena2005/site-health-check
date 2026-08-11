# Site Health Check (`site-health-check`)

A fast, lightweight CLI and Python library for web service auditing, health checks, and reconnaissance.

---

## Features

- **Status & Server Recon**: Inspects HTTP response codes, status reasons, and server banner headers.
- **Fuzzy HTML Validation**: Asserts expected strings in the response body across whitespace and newline variations.
- **Negative Assertions (Soft 404 Detection)**: Catches error messages, forbidden phrases, or maintenance indicators.
- **Flexible Execution**: Use as a Poetry CLI command, runnable module (`python -m site_health_check`), or importable Python library.
- **Nix Flake Support**: Reproducible environment support with Nix and Poetry2Nix.

---

## Installation & Setup

### Using Poetry

```bash
# Install dependencies
poetry install

# Run the test suite
poetry run pytest
```

### Using Nix

```bash
nix develop
```

---

## Usage

### 1. Command Line Interface

You can run the tool directly via Poetry scripts:

```bash
# Basic health check
poetry run site-check example.com

# Verify that a specific string is present in the HTML response
poetry run site-check example.com --string "Example Domain"

# Fail if a forbidden string is found (Soft-404 detection)
poetry run site-check example.com --string "Error 500" --exclude

# Specify custom timeout (in seconds)
poetry run site-check example.com --timeout 5
```

Alternatively, run as a module:

```bash
poetry run python -m site_health_check example.com
```

### 2. Python Library

You can also import and use the validation and checking logic programmatically:

```python
from site_health_check import perform_check, validate_html

# Run a check programmatically
response, validation_error, conn_err = perform_check(
    target_url="https://example.com",
    expected_string="Example Domain",
    must_not_have=False,
    timeout=10,
)

if response:
    print(f"Status: {response.status_code}, Server: {response.headers.get('Server')}")
```

---

## Project Structure

```text
site-health-check/
├── src/
│   └── site_health_check/
│       ├── __init__.py       # Package exports & version
│       ├── __main__.py       # python -m entrypoint
│       ├── cli.py            # CLI argument parsing & output formatting
│       └── core.py           # Core HTTP check & HTML validation logic
├── tests/
│   └── test_validator.py     # Unit test suite
├── flake.nix                 # Nix development shell & package definition
├── pyproject.toml            # Poetry packaging configuration
└── README.md
```

---

## License

[MIT](LICENSE)