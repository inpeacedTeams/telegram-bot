import os

# Все значения можно задать в Variables/Environment Variables на хостинге.
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CHANNEL = os.getenv("CHANNEL", "@oxyAPTEM")
CHANNEL_URL = os.getenv("CHANNEL_URL", "https://t.me/oxyAPTEM")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# Telegram file_id загруженных архивов проектов.
FILES = {
    "flashreply": os.getenv("FLASHREPLY_FILE_ID", ""),
    "typerx": os.getenv("TYPERX_FILE_ID", ""),
}
