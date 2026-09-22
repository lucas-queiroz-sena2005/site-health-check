import re


def validate_html(
    html_content: str,
    expected_strings: list[str] | None = None,
    undesired_strings: list[str] | None = None,
    require_all_expected: bool = True,
    reject_any_undesired: bool = True,
) -> tuple[bool, str]:
    """
    Single-pass HTML validator with early-exit short-circuiting.
    Returns (Passed: bool, Message: str).
    """
    if isinstance(expected_strings, str):
        expected_strings = [expected_strings]
    if isinstance(undesired_strings, str):
        undesired_strings = [undesired_strings]

    expected = expected_strings or []
    undesired = undesired_strings or []

    if not expected and not undesired:
        return True, "Pass: No constraints provided."

    # Compile Single Regex
    patterns: list[str] = []
    str_map: dict[str, str] = {}

    def fuzzy_escape(text: str) -> str:
        escaped = re.escape(text).replace(r"\ ", " ")
        return re.sub(r"\s+", r"\\s+", escaped)

    for i, s in enumerate(expected):
        patterns.append(f"(?P<E{i}>{fuzzy_escape(s)})")
        str_map[f"E{i}"] = s

    for i, s in enumerate(undesired):
        patterns.append(f"(?P<U{i}>{fuzzy_escape(s)})")
        str_map[f"U{i}"] = s

    regex = re.compile("|".join(patterns), flags=re.IGNORECASE)

    # State Tracking
    found_exp: set[str] = set()
    found_und: set[str] = set()
    # O(N) Execution Loop
    for match in regex.finditer(html_content):
        group_name = match.lastgroup
        if not group_name:
            continue

        matched_str = str_map[group_name]

        # Branch A: Match is Undesired
        if group_name.startswith('U'):
            found_und.add(matched_str)

            if reject_any_undesired:
                return False, f"Fail: Found undesired string '{matched_str}'."

            if len(found_und) == len(undesired):
                return False, "Fail: Found all undesired strings."

            continue

        # Branch B: Match is Expected
        found_exp.add(matched_str)

        # Early Success Exit: Only safe if there are NO undesired strings to scan for
        if not undesired:
            if not require_all_expected:
                return True, f"Pass: Found expected string '{matched_str}'."
            if len(found_exp) == len(expected):
                return True, "Pass: Found all expected strings."

    # Post-Scan Evaluation (Only reached if no early exit triggered)
    if expected:
        if require_all_expected and len(found_exp) < len(expected):
            missing = set(expected) - found_exp
            return False, f"Fail: Missing expected strings: {list(missing)}"

        if not require_all_expected and not found_exp:
            return False, "Fail: None of the expected strings were found."

    return True, "Pass: Document satisfies all conditions."
