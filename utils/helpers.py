"""
General helper functions and utilities
"""
import re
import json


def clean_text(text):
    """Remove extra spaces and normalize whitespace"""
    if not text:
        return text

    # Replace multiple spaces with single space
    text = re.sub(r' +', ' ', text)

    # Replace multiple newlines with max 2 newlines
    text = re.sub(r'\n\n\n+', '\n\n', text)

    # Remove trailing spaces on each line
    text = '\n'.join(line.rstrip() for line in text.split('\n'))

    # Strip leading/trailing whitespace from entire text
    text = text.strip()

    return text


def from_json_filter(value):
    """Parse JSON string to Python object (Jinja2 filter)"""
    if not value or value == '{}':
        return {}
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return {}
