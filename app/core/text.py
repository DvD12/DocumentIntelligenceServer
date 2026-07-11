import difflib


def normalize_tag(tag: str) -> str:
    return tag.strip().lower()


def closest_matches(value: str, candidates: list[str], n: int = 3) -> list[str]:
    return difflib.get_close_matches(value, candidates, n=n, cutoff=0.6)
