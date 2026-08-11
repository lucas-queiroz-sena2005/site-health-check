"""Core validation and auditing logic for web health checks."""

import re
from typing import Optional, Tuple
import requests


def is_valid_url(url: str) -> bool:
    """Validate whether the provided string matches a valid URL/domain pattern."""
    regex = (
        r"^(https?://)?"
        r"(([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}|localhost|\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"
        r"(:\d{1,5})?"
        r"(/[-a-zA-Z0-9@:%_\+.~#?&//=]*)?$"
    )
    return bool(re.match(regex, url))


def normalize_url(url: str) -> str:
    """Ensure URL has an http or https scheme."""
    if not url.startswith(("http://", "https://")):
        return f"http://{url}"
    return url


def validate_html(
    html_content: str, expected_string: str, must_not_have: bool = False
) -> Tuple[bool, Optional[str]]:
    """Validate presence or absence of a string in HTML content with fuzzy whitespace."""
    # Escape string but allow variable whitespace/newlines between words
    fuzzy_pattern = re.escape(expected_string).replace(r"\ ", r"\s+")
    string_found = bool(re.search(fuzzy_pattern, html_content, re.IGNORECASE))

    if must_not_have:
        if string_found:
            return False, f"Soft 404: Forbidden string '{expected_string}' was found."
        return True, None
    else:
        if not string_found:
            return False, f"Soft 404: Expected string '{expected_string}' not found."
        return True, None


def perform_check(
    target_url: str,
    expected_string: Optional[str] = None,
    must_not_have: bool = False,
    timeout: int = 10,
) -> Tuple[Optional[requests.Response], Optional[str], Optional[str]]:
    """
    Perform HTTP request and HTML validation.
    Returns (response, validation_error, connection_error).
    """
    normalized_url = normalize_url(target_url)
    try:
        response = requests.get(normalized_url, timeout=timeout, allow_redirects=True)
    except requests.RequestException as e:
        return None, None, f"Connection failed ({e})"

    validation_error = None
    if expected_string:
        _, validation_error = validate_html(response.text, expected_string, must_not_have)

    return response, validation_error, None
