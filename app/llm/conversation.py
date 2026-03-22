from __future__ import annotations

from dataclasses import dataclass

from app.retrieval.classifier import BANK_ALIASES
from app.retrieval.query_utils import detect_language, normalize_text, significant_tokens


@dataclass(slots=True)
class ConversationMatch:
    intent: str
    answer_text: str
    detected_language: str
    flow: str = "conversational"
    topic: str | None = None


class ConversationHandler:
    GREETING_PATTERNS = (
        "hello",
        "hi",
        "hey",
        "good morning",
        "good afternoon",
        "good evening",
        "barev",
        "բարև",
        "բարեւ",
        "բարև ձեզ",
        "ողջույն",
        "պարև",
        "привет",
        "здравствуйте",
        "добрый день",
        "добрый вечер",
    )
    THANKS_PATTERNS = (
        "thanks",
        "thank you",
        "thank u",
        "շնորհակալություն",
        "մերսի",
        "спасибо",
        "благодарю",
    )
    HELP_PATTERNS = (
        "help",
        "can you help",
        "how can you help",
        "what can you do",
        "what do you do",
        "what does this system do",
        "what is your job",
        "who are you",
        "օգնիր",
        "օգնեք",
        "կարող ես օգնել",
        "ինչ կարող ես անել",
        "ով ես",
        "помоги",
        "помоги пожалуйста",
        "можешь помочь",
        "чем ты можешь помочь",
        "что ты умеешь",
        "кто ты",
    )
    META_BANK_PATTERNS = (
        "which banks",
        "what banks",
        "what bank information do you have",
        "which bank information do you have",
        "what banks do you cover",
        "which banks do you cover",
        "по каким банкам",
        "какие банки",
        "с какими банками работаешь",
        "что у тебя есть по банкам",
        "ո՞ր բանկերի մասին",
        "ինչ բանկերի մասին",
        "ինչ բանկերի տվյալներ ունես",
        "որ բանկերի տվյալներ ունես",
        "ինչ բանկերի հետ ես աշխատում",
    )
    META_HOW_TO_ASK_PATTERNS = (
        "how do i ask",
        "how can i ask",
        "how should i ask",
        "how to ask",
        "how to use",
        "как спросить",
        "как задать вопрос",
        "как правильно спросить",
        "как пользоваться",
        "ինչպես հարցնել",
        "ինչպես հարց տամ",
        "ինչպես օգտվել",
        "ինչպես ճիշտ հարցնել",
    )
    META_LIMITATION_PATTERNS = (
        "why can't you answer",
        "why do you not answer",
        "why dont you answer",
        "why do you answer only",
        "why only these topics",
        "почему ты не отвечаешь",
        "почему не отвечаешь",
        "почему только эти темы",
        "почему не можешь ответить",
        "ինչու չես պատասխանում",
        "ինչու միայն այս թեմաներով",
        "ինչու չես կարող պատասխանել",
        "ինչու միայն այս հարցերով",
    )
    STATUS_PATTERNS = (
        "how are you",
        "how is it going",
        "ինչպես ես",
        "ինչ կա",
        "как дела",
        "как ты",
    )
    GOODBYE_PATTERNS = (
        "bye",
        "goodbye",
        "see you",
        "ցտեսություն",
        "հաջող",
        "пока",
        "до свидания",
    )
    ACK_PATTERNS = (
        "ok",
        "okay",
        "sure",
        "got it",
        "լավ",
        "հասկացա",
        "понятно",
        "хорошо",
        "ладно",
    )
    OPENER_PATTERNS = (
        "i have a question",
        "have a question",
        "want to ask",
        "i want to ask",
        "i want to know",
        "can i ask",
        "question please",
        "հարց ունեմ",
        "ուզում եմ հարցնել",
        "կուզեմ հարցնել",
        "ուզում եմ իմանալ",
        "կարո՞ղ եմ հարցնել",
        "у меня вопрос",
        "есть вопрос",
        "хочу спросить",
        "хочу узнать",
        "можно спросить",
    )
    BANKING_HINT_PATTERNS = (
        "bank",
        "banking",
        "բանկ",
        "банка",
        "банк",
    )
    VAGUE_INTENT_PATTERNS = (
        "want to know",
        "interested in",
        "question about",
        "have a question",
        "about ",
        "regarding",
        "հարց ունեմ",
        "ուզում եմ իմանալ",
        "ուզում եմ հարցնել",
        "հետաքրքրում է",
        "մասին",
        "есть вопрос",
        "у меня вопрос",
        "хочу узнать",
        "интересуют",
        "интересует",
        "по поводу",
        "про ",
    )
    SPECIFIC_REQUEST_PATTERNS = (
        "what",
        "which",
        "how much",
        "where",
        "list",
        "show",
        "available",
        "rate",
        "interest",
        "minimum",
        "currency",
        "address",
        "working hours",
        "schedule",
        "nearest",
        "closest",
        "ինչ",
        "որ",
        "որքա",
        "որտեղ",
        "ցույց տուր",
        "կան",
        "տոկոս",
        "նվազագույն",
        "արժույթ",
        "հասցե",
        "աշխատանքային ժամ",
        "մոտակա",
        "какие",
        "какой",
        "что",
        "сколько",
        "где",
        "покажи",
        "доступ",
        "ставк",
        "миним",
        "валют",
        "адрес",
        "график",
        "часы работы",
        "ближайш",
    )
    BRANCH_GENERIC_TOKENS = {
        "branch",
        "branches",
        "location",
        "locations",
        "address",
        "service",
        "network",
        "office",
        "atm",
        "nearest",
        "closest",
        "nearby",
        "where",
        "branch_location",
        "մասնաճյուղ",
        "մասնաճյուղեր",
        "հասցե",
        "մոտակա",
        "որտեղ",
        "բանկոմատ",
        "ֆилиал",
        "филиалы",
        "отделение",
        "адрес",
        "ближайший",
        "ближайшая",
        "где",
        "офис",
    }
    CREDITS_GENERIC_TOKENS = {
        "credit",
        "credits",
        "loan",
        "loans",
        "consumer",
        "consumer_loan",
        "consumer_credit",
        "վարկ",
        "վարկեր",
        "սպառողական",
        "кредит",
        "кредиты",
        "потребительский",
    }
    DEPOSITS_GENERIC_TOKENS = {
        "deposit",
        "deposits",
        "saving",
        "savings",
        "account",
        "time",
        "ավանդ",
        "ավանդներ",
        "խնայող",
        "депозит",
        "депозиты",
        "вклад",
        "вклады",
    }

    def match(
        self,
        question: str,
        detected_topic: str | None = None,
        detected_bank: str | None = None,
    ) -> ConversationMatch | None:
        normalized = normalize_text(question)
        if not normalized:
            return None

        detected_language = detect_language(question)

        meta_match = self._match_meta_system(normalized, detected_language)
        if meta_match:
            return meta_match

        if detected_topic:
            clarification = self._match_vague_in_scope(
                question=question,
                normalized=normalized,
                detected_topic=detected_topic,
                detected_bank=detected_bank,
                detected_language=detected_language,
            )
            if clarification:
                return clarification
            return None

        if self._matches_any(normalized, self.THANKS_PATTERNS):
            return ConversationMatch(
                intent="thanks",
                answer_text=self._localized_text(
                    detected_language,
                    hy="Խնդրեմ։ Եթե ուզում եք, կարող եք հարցնել վարկերի, ավանդների կամ մասնաճյուղերի մասին։",
                    ru="Пожалуйста. Если хотите, можете спросить про кредиты, депозиты или филиалы.",
                    en="You're welcome. If you want, you can ask about credits, deposits, or branch locations.",
                ),
                detected_language=detected_language,
            )
        if self._matches_any(normalized, self.GOODBYE_PATTERNS):
            return ConversationMatch(
                intent="goodbye",
                answer_text=self._localized_text(
                    detected_language,
                    hy="Լավ, մինչև հանդիպում։ Եթե հետո հարց ունենաք վարկերի, ավանդների կամ մասնաճյուղերի մասին, գրեք։",
                    ru="Хорошо, до связи. Если позже появится вопрос по кредитам, депозитам или филиалам, напишите.",
                    en="All right, talk to you later. If you have a question about credits, deposits, or branches later, just ask.",
                ),
                detected_language=detected_language,
            )
        if self._matches_any(normalized, self.ACK_PATTERNS):
            return ConversationMatch(
                intent="acknowledgement",
                answer_text=self._localized_text(
                    detected_language,
                    hy="Լավ։ Եթե ուզեք, կարող եք անմիջապես գրել ձեր հարցը վարկերի, ավանդների կամ մասնաճյուղերի մասին։",
                    ru="Хорошо. Можете сразу написать ваш вопрос по кредитам, депозитам или филиалам.",
                    en="All right. You can send your question directly about credits, deposits, or branch locations.",
                ),
                detected_language=detected_language,
            )
        if self._matches_any(normalized, self.STATUS_PATTERNS):
            return ConversationMatch(
                intent="status",
                answer_text=self._localized_text(
                    detected_language,
                    hy="Շնորհակալություն, լավ եմ։ Կարող եմ օգնել վարկերի, ավանդների և մասնաճյուղերի հարցերով։",
                    ru="Спасибо, всё в порядке. Я могу помочь по вопросам кредитов, депозитов и филиалов.",
                    en="Thanks, I'm doing well. I can help with questions about credits, deposits, and branch locations.",
                ),
                detected_language=detected_language,
            )
        if self._matches_any(normalized, self.HELP_PATTERNS):
            return ConversationMatch(
                intent="help",
                answer_text=self._localized_text(
                    detected_language,
                    hy=(
                        "Իհարկե, կօգնեմ։ Ես կարող եմ օգնել միայն երեք թեմայով՝ վարկեր, ավանդներ և մասնաճյուղեր։ "
                        "Պարզապես գրեք ձեր հարցը, իսկ եթե պետք լինի, ես կճշտեմ բանկը կամ մանրամասները։"
                    ),
                    ru=(
                        "Конечно, помогу. Я работаю только по трём темам: кредиты, депозиты и филиалы. "
                        "Просто напишите ваш вопрос, и если нужно, я уточню банк или детали."
                    ),
                    en=(
                        "Of course. I can help with only three topics: credits, deposits, and branch locations. "
                        "Just send your question, and if needed I'll ask for the bank or a few clarifying details."
                    ),
                ),
                detected_language=detected_language,
            )
        if self._matches_any(normalized, self.GREETING_PATTERNS):
            return ConversationMatch(
                intent="greeting",
                answer_text=self._localized_text(
                    detected_language,
                    hy=(
                        "Բարև։ Ես կարող եմ օգնել բանկային երեք թեմայով՝ վարկեր, ավանդներ և մասնաճյուղեր։ "
                        "Գրեք ձեր հարցը, և կփորձեմ օգնել։"
                    ),
                    ru=(
                        "Здравствуйте. Я могу помочь по трём банковским темам: кредиты, депозиты и филиалы. "
                        "Напишите ваш вопрос, и я постараюсь помочь."
                    ),
                    en=(
                        "Hello. I can help with three banking topics: credits, deposits, and branch locations. "
                        "Send your question and I'll do my best to help."
                    ),
                ),
                detected_language=detected_language,
            )
        if self._matches_any(normalized, self.OPENER_PATTERNS) or self._contains_banking_hint(normalized):
            return ConversationMatch(
                intent="opener",
                answer_text=self._localized_text(
                    detected_language,
                    hy=(
                        "Իհարկե, կօգնեմ։ Կարող եմ աջակցել վարկերի, ավանդների և մասնաճյուղերի հարցերով։ "
                        "Գրեք՝ կոնկրետ ինչն է ձեզ հետաքրքրում։"
                    ),
                    ru=(
                        "Конечно, помогу. Я могу подсказать по кредитам, депозитам и филиалам. "
                        "Напишите, что именно вас интересует."
                    ),
                    en=(
                        "Of course. I can help with credits, deposits, and branch locations. "
                        "Tell me what exactly you want to know."
                    ),
                ),
                detected_language=detected_language,
            )
        return None

    def _match_meta_system(self, normalized: str, detected_language: str) -> ConversationMatch | None:
        if self._matches_any(normalized, self.META_BANK_PATTERNS):
            return ConversationMatch(
                intent="meta_supported_banks",
                answer_text=self._localized_text(
                    detected_language,
                    hy=(
                        "Ես աշխատում եմ միայն պաշտոնական աղբյուրներից հավաքված տվյալներով և հիմա աջակցում եմ երեք բանկի՝ "
                        "Acba, Ameriabank և Inecobank։ Կարող եք հարցնել դրանց վարկերի, ավանդների կամ մասնաճյուղերի մասին։"
                    ),
                    ru=(
                        "Сейчас я работаю только с официальными данными по трём банкам: Acba, Ameriabank и Inecobank. "
                        "Можно спрашивать про их кредиты, депозиты и филиалы."
                    ),
                    en=(
                        "Right now I work only with official data for three banks: Acba, Ameriabank, and Inecobank. "
                        "You can ask about their credits, deposits, or branch locations."
                    ),
                ),
                detected_language=detected_language,
            )
        if self._matches_any(normalized, self.META_HOW_TO_ASK_PATTERNS):
            return ConversationMatch(
                intent="meta_how_to_ask",
                answer_text=self._localized_text(
                    detected_language,
                    hy=(
                        "Կարող եք հարցնել բնական ձևով։ Օրինակ՝ գրեք կամ ասեք, թե որ բանկի ավանդներն են ձեզ հետաքրքրում, "
                        "ինչ սպառողական վարկեր կան, կամ որտեղ է գտնվում կոնկրետ մասնաճյուղը։ Եթե հարցը շատ ընդհանուր լինի, ես կճշտեմ բանկը կամ մանրամասը։"
                    ),
                    ru=(
                        "Можете задавать вопрос обычным языком. Например: какие депозиты есть у Acba, какие потребительские кредиты доступны, "
                        "или где находится нужный филиал. Если вопрос будет слишком общий, я сам уточню банк или детали."
                    ),
                    en=(
                        "You can ask in plain language. For example: which deposits Acba offers, what consumer loans are available, "
                        "or where a specific branch is located. If the question is too broad, I'll ask for the bank or a few details."
                    ),
                ),
                detected_language=detected_language,
            )
        if self._matches_any(normalized, self.META_LIMITATION_PATTERNS):
            return ConversationMatch(
                intent="meta_scope_limits",
                answer_text=self._localized_text(
                    detected_language,
                    hy=(
                        "Ես հատուկ սահմանափակված եմ երեք թեմայով՝ վարկեր, ավանդներ և մասնաճյուղեր, և պատասխանում եմ միայն պաշտոնական աղբյուրների հիման վրա։ "
                        "Եթե հարցը դուրս է այդ շրջանակից կամ տվյալը չկա բազայում, ես դա բաց կասեմ ու կօգնեմ ձևակերպել հարցը այդ թեմաների մեջ։"
                    ),
                    ru=(
                        "Я специально ограничен тремя темами: кредиты, депозиты и филиалы, и отвечаю только по официальным источникам. "
                        "Если вопрос вне этих тем или нужных данных нет в базе, я прямо скажу об этом и помогу сузить вопрос."
                    ),
                    en=(
                        "I'm intentionally limited to three topics: credits, deposits, and branch locations, and I answer only from official sources. "
                        "If a question is outside that scope or the data is missing, I'll say so clearly and help narrow the question."
                    ),
                ),
                detected_language=detected_language,
            )
        return None

    def _match_vague_in_scope(
        self,
        *,
        question: str,
        normalized: str,
        detected_topic: str,
        detected_bank: str | None,
        detected_language: str,
    ) -> ConversationMatch | None:
        if detected_topic == "branch_locations":
            if self._has_specific_branch_reference(question, detected_bank):
                return None
            if detected_bank:
                answer = self._localized_text(
                    detected_language,
                    hy=f"Կօգնեմ։ Նշեք, խնդրում եմ, քաղաքը կամ մասնաճյուղի անունը {detected_bank}-ի համար, օրինակ՝ Arabkir, որպեսզի գտնեմ ճիշտ հասցեն։",
                    ru=f"Помогу. Уточните, пожалуйста, город или название филиала для {detected_bank}, например Arabkir, чтобы я нашёл точный адрес.",
                    en=f"I can help. Please specify the city or branch name for {detected_bank}, for example Arabkir, so I can find the exact address.",
                )
            else:
                answer = self._localized_text(
                    detected_language,
                    hy="Կօգնեմ։ Նշեք, խնդրում եմ, որ բանկի և որ քաղաքի կամ մասնաճյուղի մասին եք հարցնում։ Ես կարող եմ օգնել Acba, Ameriabank և Inecobank մասնաճյուղերի հարցերով։",
                    ru="Помогу. Уточните, пожалуйста, какой банк и какой город или филиал вас интересуют. Я могу помочь по филиалам Acba, Ameriabank и Inecobank.",
                    en="I can help. Please specify which bank and which city or branch you mean. I can help with Acba, Ameriabank, and Inecobank branch questions.",
                )
            return ConversationMatch(
                intent="clarify_branch_locations",
                answer_text=answer,
                detected_language=detected_language,
                flow="clarification",
                topic=detected_topic,
            )

        if self._has_specific_request(normalized):
            return None

        if not self._looks_like_vague_topic_intent(question, normalized, detected_topic):
            return None

        if detected_topic == "credits":
            answer = self._localized_credit_clarification(detected_language, detected_bank)
        else:
            answer = self._localized_deposit_clarification(detected_language, detected_bank)

        return ConversationMatch(
            intent=f"clarify_{detected_topic}",
            answer_text=answer,
            detected_language=detected_language,
            flow="clarification",
            topic=detected_topic,
        )

    def _looks_like_vague_topic_intent(self, question: str, normalized: str, detected_topic: str) -> bool:
        if self._matches_any(normalized, self.VAGUE_INTENT_PATTERNS):
            return True

        generic_token_sets = {
            "credits": self.CREDITS_GENERIC_TOKENS,
            "deposits": self.DEPOSITS_GENERIC_TOKENS,
        }
        topic_tokens = generic_token_sets.get(detected_topic)
        if not topic_tokens:
            return False

        meaningful_tokens = [
            token
            for token in significant_tokens(question)
            if not self._is_generic_token(token, topic_tokens)
            and not self._is_generic_token(token, self._normalized_bank_aliases())
        ]
        return len(meaningful_tokens) == 0

    def _has_specific_request(self, normalized: str) -> bool:
        return self._matches_any(normalized, self.SPECIFIC_REQUEST_PATTERNS)

    def _has_specific_branch_reference(self, question: str, detected_bank: str | None) -> bool:
        meaningful_tokens = []
        bank_tokens = self._normalized_bank_aliases()
        for token in significant_tokens(question):
            if self._is_generic_token(token, self.BRANCH_GENERIC_TOKENS):
                continue
            if self._is_generic_token(token, bank_tokens):
                continue
            meaningful_tokens.append(token)
        if detected_bank and not meaningful_tokens:
            return False
        return bool(meaningful_tokens)

    def _contains_banking_hint(self, normalized: str) -> bool:
        return self._matches_any(normalized, self.BANKING_HINT_PATTERNS)

    def _localized_credit_clarification(self, language: str, detected_bank: str | None) -> str:
        if detected_bank:
            return self._localized_text(
                language,
                hy=f"Իհարկե, կօգնեմ։ Ի՞նչն է ձեզ հետաքրքրում {detected_bank}-ի վարկերի մասին՝ տեսակները, պայմանները, թե տոկոսադրույքը։",
                ru=f"Конечно, помогу. Что именно вас интересует по кредитам {detected_bank}: виды, условия или процентная ставка?",
                en=f"Of course. What exactly would you like to know about {detected_bank} credits: the available types, the conditions, or the interest rate?",
            )
        return self._localized_text(
            language,
            hy="Իհարկե, կօգնեմ։ Ո՞ր բանկի վարկերն են ձեզ հետաքրքրում՝ Acba, Ameriabank, թե Inecobank։",
            ru="Конечно, помогу. Кредиты какого банка вас интересуют: Acba, Ameriabank или Inecobank?",
            en="Of course. Which bank's credits are you interested in: Acba, Ameriabank, or Inecobank?",
        )

    def _localized_deposit_clarification(self, language: str, detected_bank: str | None) -> str:
        if detected_bank:
            return self._localized_text(
                language,
                hy=f"Իհարկե, կօգնեմ։ Ի՞նչն է ձեզ հետաքրքրում {detected_bank}-ի ավանդների մասին՝ տեսակները, տոկոսադրույքը, ժամկետը, թե նվազագույն գումարը։",
                ru=f"Конечно, помогу. Что именно вас интересует по депозитам {detected_bank}: виды, ставка, срок или минимальная сумма?",
                en=f"Of course. What exactly would you like to know about {detected_bank} deposits: the available products, the rate, the term, or the minimum amount?",
            )
        return self._localized_text(
            language,
            hy="Իհարկե, կօգնեմ։ Ո՞ր բանկի ավանդներն են ձեզ հետաքրքրում՝ Acba, Ameriabank, թե Inecobank։",
            ru="Конечно, помогу. Депозиты какого банка вас интересуют: Acba, Ameriabank или Inecobank?",
            en="Of course. Which bank's deposits are you interested in: Acba, Ameriabank, or Inecobank?",
        )

    def _localized_text(self, detected_language: str, *, hy: str, ru: str, en: str) -> str:
        if detected_language == "ru":
            return ru
        if detected_language == "en":
            return en
        return hy

    @staticmethod
    def _matches_any(normalized_text: str, patterns: tuple[str, ...]) -> bool:
        return any(normalize_text(pattern) in normalized_text for pattern in patterns)

    @staticmethod
    def _normalized_bank_aliases() -> tuple[str, ...]:
        aliases: list[str] = []
        for bank_aliases in BANK_ALIASES.values():
            aliases.extend(normalize_text(alias) for alias in bank_aliases)
        return tuple(dict.fromkeys(alias for alias in aliases if alias))

    @staticmethod
    def _is_generic_token(token: str, generic_tokens: set[str] | tuple[str, ...]) -> bool:
        return any(
            token == generic_token
            or token.startswith(generic_token)
            or generic_token.startswith(token)
            for generic_token in generic_tokens
            if generic_token
        )
