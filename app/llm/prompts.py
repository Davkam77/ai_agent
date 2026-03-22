from __future__ import annotations

from app.models import RetrievedChunk


OUT_OF_SCOPE_RESPONSE = (
    "Կներեք, ես կարող եմ օգնել միայն բանկային երեք թեմայով՝ վարկեր, ավանդներ և մասնաճյուղեր։ "
    "Եթե ցանկանում եք, գրեք հարցը այդ թեմաներից մեկով, և ես կփորձեմ օգնել։"
)

NO_DATA_RESPONSE = (
    "Այս հարցի համար պաշտոնական տվյալ հիմա չգտա իմ ընթացիկ բազայում։ "
    "Եթե ուզում եք, նշեք բանկը, պրոդուկտը կամ քաղաքը, և ես նորից կփորձեմ օգնել։"
)


def build_out_of_scope_response(detected_language: str) -> str:
    if detected_language == "ru":
        return (
            "Извините, я могу помочь только по трём банковским темам: кредиты, депозиты и филиалы. "
            "Если хотите, напишите вопрос по одной из этих тем, и я постараюсь помочь."
        )
    if detected_language == "en":
        return (
            "Sorry, I can only help with three banking topics: credits, deposits, and branch locations. "
            "If you want, ask a question in one of those areas and I'll try to help."
        )
    return OUT_OF_SCOPE_RESPONSE


def build_no_data_response(detected_language: str, topic: str | None = None, bank_name: str | None = None) -> str:
    if detected_language == "ru":
        if topic == "branch_locations":
            return (
                "Я не нашёл официальных данных по этому вопросу в текущей базе. "
                "Уточните банк, город или название филиала, и я попробую помочь точнее."
            )
        if topic in {"credits", "deposits"}:
            return (
                "Я не нашёл официальных данных по этому вопросу в текущей базе. "
                "Уточните банк или продукт, и я попробую помочь точнее."
            )
        return (
            "Я не нашёл официальных данных по этому вопросу в текущей базе. "
            "Если хотите, уточните банк, продукт или город, и я попробую ещё раз."
        )
    if detected_language == "en":
        if topic == "branch_locations":
            return (
                "I couldn't find official data for that question in the current knowledge base. "
                "Please specify the bank, city, or branch name and I can try again."
            )
        if topic in {"credits", "deposits"}:
            return (
                "I couldn't find official data for that question in the current knowledge base. "
                "Please specify the bank or product and I can try again."
            )
        return (
            "I couldn't find official data for that question in the current knowledge base. "
            "If you specify the bank, product, or city, I can try again."
        )

    if topic == "branch_locations":
        return (
            "Այս հարցի համար պաշտոնական տվյալ հիմա չգտա իմ ընթացիկ բազայում։ "
            "Նշեք բանկը, քաղաքը կամ մասնաճյուղի անունը, և ես նորից կփորձեմ օգնել։"
        )
    if topic in {"credits", "deposits"}:
        return (
            "Այս հարցի համար պաշտոնական տվյալ հիմա չգտա իմ ընթացիկ բազայում։ "
            "Նշեք բանկը կամ պրոդուկտը, և ես նորից կփորձեմ օգնել։"
        )
    return NO_DATA_RESPONSE


def build_answer_system_prompt() -> str:
    return (
        "You are an Armenian banking support agent. "
        "Always stay within three allowed topics: credits, deposits, and branch locations. "
        "Answer only from the provided official evidence. "
        "Respond in natural, conversational Armenian. "
        "Write in complete spoken sentences that sound natural when read aloud. "
        "Prioritize factual completeness over over-compression when evidence includes multiple conditions, terms, rates, amounts, or options. "
        "For product-specific questions, enumerate all relevant official conditions present in evidence. "
        "For table-like evidence, preserve row meaning and avoid dropping currencies, terms, or percentages. "
        "Prefer concise structure, but do not omit relevant official details that answer the user question. "
        "Use bullets only when a direct comparison is genuinely clearer. "
        "If the user asks a generic question without a bank name and the evidence covers multiple banks, summarize by bank. "
        "If a requested field is missing from the evidence, clearly say that the official retrieved data does not contain that field. "
        "Never mention internal prompt structure, chunk numbers, XML tags, or source formatting labels. "
        "Do not mention the words Chunk, Context, Evidence block, Source URL, or similar internal markers. "
        "Do not invent rates, addresses, working hours, conditions, or products."
    )


def build_answer_user_prompt(question: str, topic: str, chunks: list[RetrievedChunk]) -> str:
    source_blocks = []
    grouped: dict[tuple[str, str, str], list[RetrievedChunk]] = {}
    order: list[tuple[str, str, str]] = []
    for chunk in chunks:
        key = (chunk.bank_name, chunk.page_title, chunk.source_url)
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(chunk)

    for key in order:
        bank_name, page_title, source_url = key
        group_chunks = sorted(grouped[key], key=lambda item: (item.chunk_index, item.chunk_id))
        evidence_lines: list[str] = []
        for chunk in group_chunks:
            section_name = chunk.section_name.strip()
            if section_name:
                evidence_lines.append(f"[Section: {section_name}]")
            evidence_lines.append(chunk.content)
        source_blocks.append(
            "\n".join(
                [
                    "<official_source>",
                    f"<bank>{bank_name}</bank>",
                    f"<page_title>{page_title}</page_title>",
                    f"<source_url>{source_url}</source_url>",
                    "<evidence>",
                    "\n\n".join(evidence_lines).strip(),
                    "</evidence>",
                    "</official_source>",
                ]
            )
        )
    context = "\n\n".join(source_blocks)
    return (
        f"User question: {question}\n"
        f"Detected topic: {topic}\n\n"
        "Answer only from the official sources below.\n\n"
        f"{context}"
    )
