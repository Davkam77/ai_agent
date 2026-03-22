from __future__ import annotations

from app.models import Topic
from app.retrieval.query_utils import normalize_text


TOPIC_KEYWORDS: dict[Topic, tuple[str, ...]] = {
    Topic.CREDITS: (
        "loan",
        "loans",
        "credit",
        "credits",
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
        "кредит",
        "кредиты",
        "потребительский кредит",
        "потребительские кредиты",
        "овердрафт",
    ),
    Topic.DEPOSITS: (
        "deposit",
        "deposits",
        "saving",
        "savings",
        "time deposit",
        "savings account",
        "ավանդ",
        "ավանդներ",
        "ժամկետային ավանդ",
        "խնայողություն",
        "депозит",
        "депозиты",
        "вклад",
        "вклады",
        "сбережения",
    ),
    Topic.BRANCH_LOCATIONS: (
        "branch",
        "branches",
        "atm",
        "office",
        "address",
        "location",
        "map",
        "service network",
        "working hours",
        "branch location",
        "մասնաճյուղ",
        "մասնաճյուղեր",
        "հասցե",
        "քարտեզ",
        "աշխատանքային ժամ",
        "բանկոմատ",
        "филиал",
        "филиалы",
        "отделение",
        "адрес",
        "локация",
        "карта",
        "часы работы",
        "банкомат",
        "офис",
    ),
}

BANK_ALIASES: dict[str, tuple[str, ...]] = {
    "Acba": (
        "acba",
        "acba bank",
        "ակբա",
        "ակբա բանկ",
        "акба",
        "акба банк",
    ),
    "Ameriabank": (
        "ameriabank",
        "ameria",
        "ameria bank",
        "ամերիաբանկ",
        "ամերիա",
        "америабанк",
        "америя",
        "америя банк",
    ),
    "Inecobank": (
        "inecobank",
        "ineco",
        "ineco bank",
        "ինեկոբանկ",
        "ինեկո",
        "инекобанк",
        "инеко",
        "инекo банк",
    ),
}

_NORMALIZED_TOPIC_KEYWORDS: dict[Topic, tuple[str, ...]] = {
    topic: tuple(normalize_text(keyword) for keyword in keywords)
    for topic, keywords in TOPIC_KEYWORDS.items()
}
_NORMALIZED_BANK_ALIASES: dict[str, tuple[str, ...]] = {
    bank_name: tuple(sorted((normalize_text(alias) for alias in aliases), key=len, reverse=True))
    for bank_name, aliases in BANK_ALIASES.items()
}


class TopicClassifier:
    def classify(self, question: str) -> str | None:
        lowered = normalize_text(question)
        scores: dict[Topic, int] = {}
        for topic, keywords in _NORMALIZED_TOPIC_KEYWORDS.items():
            score = sum(1 for keyword in keywords if keyword and keyword in lowered)
            if score:
                scores[topic] = score
        if not scores:
            return None
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
            return None
        return ranked[0][0].value

    def detect_bank(self, question: str) -> str | None:
        lowered = normalize_text(question)
        for bank_name, aliases in _NORMALIZED_BANK_ALIASES.items():
            if any(alias and alias in lowered for alias in aliases):
                return bank_name
        return None
