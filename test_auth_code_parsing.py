#!/usr/bin/env python3
"""
Test script to verify auth code parsing from various formats
"""
import json


def parse_auth_code(raw_input: str) -> str:
    """
    Parse authorization code from various input formats:
    1. Full JSON response: {"authorizationCode": "...", ...}
    2. Code in quotes: "01fec44ab47f47a1a62a5a325765046f"
    3. Plain code: 01fec44ab47f47a1a62a5a325765046f

    Returns the clean authorization code
    """
    if not raw_input:
        return ""

    # Strip leading/trailing whitespace
    raw_input = raw_input.strip()

    # Try to parse as JSON first
    try:
        data = json.loads(raw_input)
        # Check if it's a dict with authorizationCode field
        if isinstance(data, dict) and "authorizationCode" in data:
            code = data["authorizationCode"]
            if code:  # Make sure it's not null
                print("  → Parsed from JSON format")
                return str(code).strip()
    except (json.JSONDecodeError, ValueError):
        # Not JSON, continue with other parsing methods
        pass

    # Remove quotes if present (handles both single and double quotes)
    if (raw_input.startswith('"') and raw_input.endswith('"')) or \
       (raw_input.startswith("'") and raw_input.endswith("'")):
        code = raw_input[1:-1].strip()
        print("  → Parsed from quoted format")
        return code

    # Return as-is (plain code format)
    print("  → Parsed from plain format")
    return raw_input


def test_parse_auth_code():
    """Test the parse_auth_code function with various input formats"""

    print("Testing auth code parsing...")
    print("=" * 60)

    tests_passed = 0
    tests_total = 0

    # Test 1: Full JSON response
    tests_total += 1
    json_input = '{"warning":"Do not share this code with any 3rd party service. It allows full access to your Epic account.","redirectUrl":"https://accounts.epicgames.com/fnauth?code=01fec44ab47f47a1a62a5a325765046f","authorizationCode":"01fec44ab47f47a1a62a5a325765046f","exchangeCode":null,"sid":null}'
    result = parse_auth_code(json_input)
    expected = "01fec44ab47f47a1a62a5a325765046f"
    print(f"\nTest 1 - Full JSON:")
    print(f"  Input: {json_input[:60]}...")
    print(f"  Result: '{result}'")
    print(f"  Expected: '{expected}'")
    if result == expected:
        print(f"  ✓ PASS")
        tests_passed += 1
    else:
        print(f"  ✗ FAIL")

    # Test 2: Plain code
    tests_total += 1
    plain_input = "01fec44ab47f47a1a62a5a325765046f"
    result = parse_auth_code(plain_input)
    expected = "01fec44ab47f47a1a62a5a325765046f"
    print(f"\nTest 2 - Plain code:")
    print(f"  Input: '{plain_input}'")
    print(f"  Result: '{result}'")
    print(f"  Expected: '{expected}'")
    if result == expected:
        print(f"  ✓ PASS")
        tests_passed += 1
    else:
        print(f"  ✗ FAIL")

    # Test 3: Code in double quotes
    tests_total += 1
    quoted_input = '"01fec44ab47f47a1a62a5a325765046f"'
    result = parse_auth_code(quoted_input)
    expected = "01fec44ab47f47a1a62a5a325765046f"
    print(f"\nTest 3 - Code in double quotes:")
    print(f"  Input: {quoted_input}")
    print(f"  Result: '{result}'")
    print(f"  Expected: '{expected}'")
    if result == expected:
        print(f"  ✓ PASS")
        tests_passed += 1
    else:
        print(f"  ✗ FAIL")

    # Test 4: Code in single quotes
    tests_total += 1
    quoted_input = "'01fec44ab47f47a1a62a5a325765046f'"
    result = parse_auth_code(quoted_input)
    expected = "01fec44ab47f47a1a62a5a325765046f"
    print(f"\nTest 4 - Code in single quotes:")
    print(f"  Input: {quoted_input}")
    print(f"  Result: '{result}'")
    print(f"  Expected: '{expected}'")
    if result == expected:
        print(f"  ✓ PASS")
        tests_passed += 1
    else:
        print(f"  ✗ FAIL")

    # Test 5: Code with whitespace
    tests_total += 1
    whitespace_input = "  01fec44ab47f47a1a62a5a325765046f  "
    result = parse_auth_code(whitespace_input)
    expected = "01fec44ab47f47a1a62a5a325765046f"
    print(f"\nTest 5 - Code with whitespace:")
    print(f"  Input: '{whitespace_input}'")
    print(f"  Result: '{result}'")
    print(f"  Expected: '{expected}'")
    if result == expected:
        print(f"  ✓ PASS")
        tests_passed += 1
    else:
        print(f"  ✗ FAIL")

    # Test 6: Empty string
    tests_total += 1
    empty_input = ""
    result = parse_auth_code(empty_input)
    expected = ""
    print(f"\nTest 6 - Empty string:")
    print(f"  Input: '{empty_input}'")
    print(f"  Result: '{result}'")
    print(f"  Expected: '{expected}'")
    if result == expected:
        print(f"  ✓ PASS")
        tests_passed += 1
    else:
        print(f"  ✗ FAIL")

    # Test 7: Quoted code with whitespace
    tests_total += 1
    quoted_ws_input = '  "01fec44ab47f47a1a62a5a325765046f"  '
    result = parse_auth_code(quoted_ws_input)
    expected = "01fec44ab47f47a1a62a5a325765046f"
    print(f"\nTest 7 - Quoted code with surrounding whitespace:")
    print(f"  Input: '{quoted_ws_input}'")
    print(f"  Result: '{result}'")
    print(f"  Expected: '{expected}'")
    if result == expected:
        print(f"  ✓ PASS")
        tests_passed += 1
    else:
        print(f"  ✗ FAIL")

    print("\n" + "=" * 60)
    print(f"Tests passed: {tests_passed}/{tests_total}")

    if tests_passed == tests_total:
        print("✓ All tests passed!")
        return 0
    else:
        print("✗ Some tests failed")
        return 1


if __name__ == "__main__":
    exit(test_parse_auth_code())
