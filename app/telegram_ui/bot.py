from __future__ import annotations

import logging
from collections import OrderedDict

from telegram import Update
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

from app.config.settings import Settings
from app.llm.prompts import OUT_OF_SCOPE_RESPONSE
from app.llm.service import SupportAgentService

logger = logging.getLogger(__name__)

START_MESSAGE = (
    "Բարև։ Սա Armenian Voice AI Support Agent-ի Telegram տեքստային demo-ն է։ "
    "Այստեղ կարող եք գրել միայն ավանդների, վարկերի և մասնաճյուղերի մասին հարցեր։ "
    "Ձայնային demo-ն աշխատում է LiveKit OSS runtime-ով, ոչ թե Telegram-ում։"
)

HELP_MESSAGE = (
    "Telegram demo-ում այժմ աջակցվում են միայն տեքստային հարցերը երեք թեմայով՝ "
    "ավանդներ, վարկեր և մասնաճյուղեր։ "
    "Ձայնային փորձարկման համար գործարկեք LiveKit voice runtime-ը և միացեք համապատասխան room-ին։"
)

VOICE_NOT_READY_MESSAGE = (
    "Telegram demo-ն այս նախագծում աջակցում է միայն տեքստային հարցումներ։ "
    "Ձայնային demo-ն աշխատում է LiveKit OSS runtime-ով, ոչ թե Telegram voice/audio հաղորդագրություններով։ "
    "Եթե ուզում եք voice flow, գործարկեք LiveKit runtime-ը և միացեք համապատասխան room-ին։"
)


class TelegramDemoBot:
    def __init__(self, settings: Settings, support_agent: SupportAgentService) -> None:
        self.settings = settings
        self.support_agent = support_agent
        self._processed_updates: OrderedDict[str, None] = OrderedDict()
        self._max_processed_updates = 4096

    def build_application(self) -> Application:
        if not self.settings.telegram_bot_token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is required to run the demo bot.")

        application = ApplicationBuilder().token(self.settings.telegram_bot_token).build()
        application.add_handler(CommandHandler("start", self._handle_start))
        application.add_handler(CommandHandler("help", self._handle_help))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_text))
        application.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, self._handle_voice))
        return application

    def run(self) -> None:
        self.build_application().run_polling()

    async def _handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or self._is_duplicate_update(update):
            return
        await update.message.reply_text(START_MESSAGE)

    async def _handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or self._is_duplicate_update(update):
            return
        await update.message.reply_text(HELP_MESSAGE)

    async def _handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.message.text:
            return
        if self._is_duplicate_update(update):
            logger.info("Skipping duplicate Telegram update %s", update.update_id)
            return

        question = update.message.text.strip()
        if not question:
            await update.message.reply_text(OUT_OF_SCOPE_RESPONSE)
            return

        result = self.support_agent.answer_question(question)
        await update.message.reply_text(result.answer_text)

    async def _handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or self._is_duplicate_update(update):
            return
        await update.message.reply_text(VOICE_NOT_READY_MESSAGE)

    def _is_duplicate_update(self, update: Update) -> bool:
        keys = self._update_keys(update)
        if not keys:
            return False
        if any(key in self._processed_updates for key in keys):
            return True
        for key in keys:
            self._processed_updates[key] = None
            self._processed_updates.move_to_end(key)
        while len(self._processed_updates) > self._max_processed_updates:
            self._processed_updates.popitem(last=False)
        return False

    @staticmethod
    def _update_keys(update: Update) -> list[str]:
        keys: list[str] = []
        if update.update_id is not None:
            keys.append(f"update:{update.update_id}")
        message = update.effective_message
        chat = update.effective_chat
        message_id = getattr(message, "message_id", None)
        chat_id = getattr(chat, "id", None)
        if chat_id is not None and message_id is not None:
            keys.append(f"message:{chat_id}:{message_id}")
        return keys
