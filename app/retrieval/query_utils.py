from __future__ import annotations

import re
import unicodedata


TOKEN_RE = re.compile(r"[0-9a-z\u0400-\u04ff\u0531-\u058f]+", re.IGNORECASE)

PUNCTUATION_TRANSLATION = str.maketrans(
    {
        "\n": " ",
        "\r": " ",
        "\t": " ",
        "-": " ",
        "_": " ",
        "/": " ",
        "\\": " ",
        ",": " ",
        ".": " ",
        ":": " ",
        ";": " ",
        "!": " ",
        "?": " ",
        "(": " ",
        ")": " ",
        "[": " ",
        "]": " ",
        "{": " ",
        "}": " ",
        "\"": " ",
        "'": " ",
        "`": " ",
        "«": " ",
        "»": " ",
        "“": " ",
        "”": " ",
        "„": " ",
        "’": " ",
        "–": " ",
        "—": " ",
        "։": " ",
        "՞": " ",
        "՜": " ",
        "՝": " ",
        "՛": " ",
        "…": " ",
    }
)

COMMON_ARMENIAN_SUFFIXES = (
    "ներով",
    "ները",
    "ներին",
    "ներից",
    "ների",
    "երում",
    "երով",
    "երին",
    "երից",
    "երի",
    "ությամբ",
    "ություն",
    "ագույն",
    "ական",
    "ապես",
    "ումը",
    "ումով",
    "ումն",
    "ում",
    "ից",
    "ով",
    "ին",
    "ի",
    "ը",
    "ն",
    "եր",
    "ներ",
)

STOPWORDS = {
    "a",
    "about",
    "an",
    "and",
    "are",
    "at",
    "bank",
    "banks",
    "can",
    "do",
    "does",
    "for",
    "from",
    "has",
    "have",
    "hints",
    "how",
    "i",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "official",
    "on",
    "or",
    "supported",
    "tell",
    "the",
    "their",
    "there",
    "these",
    "this",
    "to",
    "topic",
    "what",
    "where",
    "which",
    "who",
    "with",
    "you",
    "է",
    "էի",
    "եմ",
    "են",
    "ենք",
    "էիք",
    "թե",
    "ու",
    "որ",
    "որը",
    "որոնք",
    "ինչ",
    "ինչպես",
    "որքան",
    "քանի",
    "որտեղ",
    "մեջ",
    "համար",
    "մասին",
    "կա",
    "կան",
    "ունի",
    "գտնվում",
    "բացել",
    "բացելու",
    "իմ",
    "ձեզ",
    "ինձ",
    "մենք",
    "դուք",
    "նա",
    "նրանք",
    "էլ",
    "իսկ",
    "մոտ",
}

TOPIC_QUERY_HINTS: dict[str, tuple[str, ...]] = {
    "credits": (
        "credit",
        "credits",
        "loan",
        "loans",
        "consumer loan",
        "consumer loans",
        "consumer credit",
        "consumer credits",
        "overdraft",
        "վարկ",
        "վարկեր",
        "սպառողական վարկ",
        "սպառողական վարկեր",
        "օվերդրաֆտ",
    ),
    "deposits": (
        "deposit",
        "deposits",
        "saving",
        "savings",
        "savings account",
        "time deposit",
        "interest rate",
        "minimum amount",
        "ավանդ",
        "ավանդներ",
        "խնայողություն",
        "տոկոսադրույք",
        "նվազագույն գումար",
    ),
    "branch_locations": (
        "branch",
        "branches",
        "branch location",
        "address",
        "service network",
        "location",
        "working hours",
        "atm",
        "office",
        "մասնաճյուղ",
        "մասնաճյուղեր",
        "հասցե",
        "տեղակայություն",
        "աշխատանքային ժամեր",
        "բանկոմատ",
    ),
}


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = normalized.translate(PUNCTUATION_TRANSLATION)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def detect_language(text: str) -> str:
    armenian_chars = sum(1 for char in text if "\u0531" <= char <= "\u058f")
    cyrillic_chars = sum(1 for char in text if "\u0400" <= char <= "\u04ff")
    latin_chars = sum(1 for char in text if char.isascii() and char.isalpha())
    if armenian_chars and latin_chars:
        return "mixed"
    if armenian_chars:
        return "hy"
    if cyrillic_chars:
        return "ru"
    if latin_chars:
        return "en"
    return "unknown"


def tokenize_text(text: str) -> list[str]:
    normalized = normalize_text(text)
    tokens = TOKEN_RE.findall(normalized)
    expanded: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        for variant in expand_token_variants(token):
            if variant in seen:
                continue
            seen.add(variant)
            expanded.append(variant)
    return expanded


def significant_tokens(text: str) -> list[str]:
    return [token for token in tokenize_text(text) if token not in STOPWORDS and len(token) > 1]


def expand_token_variants(token: str) -> list[str]:
    variants = [token]
    if len(token) > 4 and token.endswith("s"):
        variants.append(token[:-1])
    for suffix in COMMON_ARMENIAN_SUFFIXES:
        if not token.endswith(suffix):
            continue
        stem = token[: -len(suffix)]
        if len(stem) < 3:
            continue
        variants.append(stem)
    deduped: list[str] = []
    seen: set[str] = set()
    for variant in variants:
        if variant in seen:
            continue
        seen.add(variant)
        deduped.append(variant)
    return deduped


def build_retrieval_query(question: str, topic: str, bank_name: str | None = None, bank_aliases: tuple[str, ...] = ()) -> str:
    parts = [question.strip()]
    hints = ", ".join(TOPIC_QUERY_HINTS.get(topic, ()))
    if hints:
        parts.append(f"Supported topic: {topic}")
        parts.append(f"Topic hints: {hints}")
    if bank_name:
        alias_text = ", ".join(item for item in (bank_name, *bank_aliases) if item)
        parts.append(f"Bank hints: {alias_text}")
    return "\n".join(part for part in parts if part)
