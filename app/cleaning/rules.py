from __future__ import annotations


GLOBAL_EXACT_NOISE = {
    "Search",
    "Subscribe",
    "Main",
    "More",
    "Help",
    "Learn more",
    "Read more",
    "Download",
    "FAQ",
    "Map List",
    "Retail",
    "Business",
    "Universal",
    "Map",
    "Branches",
    "ATMs",
    "INECOPAY",
    "Apply now",
}

GLOBAL_CONTAINS_NOISE = (
    "all rights reserved",
    "created by",
    "privacy policy",
    "customer rights",
    "financial system mediator",
    "bank takes no responsibility",
    "supervised by the central bank",
    "supervised by the cba",
    "dear customer, please kindly note",
)

BANK_TOPIC_EXACT_NOISE: dict[tuple[str, str], set[str]] = {
    ("Acba", "credits"): {"Special offers", "Save and invest", "Choose your card"},
    ("Acba", "deposits"): {"Special offers", "Get a loan", "Choose your card"},
    ("Ameriabank", "credits"): {"Search", "MyAmeria", "Subscribe"},
    ("Ameriabank", "deposits"): {"Search", "MyAmeria", "Subscribe"},
}
