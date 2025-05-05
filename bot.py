import os
import logging
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, CallbackQueryHandler
from telegram import Update, ParseMode
from database import setup_database
from handlers import (
    start_handler, help_handler, message_handler, verify_payment_handler,
    add_resource_handler, admin_verify_payment_handler, stats_handler,
    grant_access_handler, button_callback_handler, process_resource_conversation,
    remove_resource_handler, edit_resource_handler, delete_subject_handler,
    upload_json_handler, process_json_upload, my_history_handler, admin_panel_handler,
    animate_resource_loading
)

logger = logging.getLogger(__name__)

def setup_bot():
    """Set up and start the Telegram bot."""
    # Get bot token from environment variable
    bot_token = os.environ.get("BOT_TOKEN")
    if not bot_token:
        logger.error("No bot token found in environment variables!")
        raise ValueError("BOT_TOKEN not found")

    # Create the Updater and pass it the bot's token
    updater = Updater(bot_token, use_context=True)

    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    # Ensure database is set up
    setup_database()

    # Register command handlers
    dp.add_handler(CommandHandler("start", start_handler))
    dp.add_handler(CommandHandler("help", help_handler))
    dp.add_handler(CommandHandler("my_history", my_history_handler))
    dp.add_handler(CommandHandler("verify_payment", verify_payment_handler))
    dp.add_handler(CommandHandler("add_resource", add_resource_handler))
    dp.add_handler(CommandHandler("verify", admin_verify_payment_handler))
    dp.add_handler(CommandHandler("stats", stats_handler))
    dp.add_handler(CommandHandler("admin", admin_panel_handler))
    dp.add_handler(CommandHandler("grant_access", grant_access_handler))
    
    # Register the new resource management commands
    dp.add_handler(CommandHandler("remove_resource", remove_resource_handler))
    dp.add_handler(CommandHandler("edit_resource", edit_resource_handler))
    dp.add_handler(CommandHandler("delete_subject", delete_subject_handler))
    dp.add_handler(CommandHandler("upload_json", upload_json_handler))
    
    # Register document handler for JSON uploads
    dp.add_handler(MessageHandler(Filters.document.file_extension("json"), process_json_upload))

    # Register message handlers in order of precedence
    # First check if it's part of a resource addition conversation
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, process_resource_conversation))
    # Then process normal messages with subject code detection
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, message_handler))
    
    # Register callback query handler for inline keyboard buttons
    dp.add_handler(CallbackQueryHandler(button_callback_handler))

    # Log all errors
    dp.add_error_handler(error_handler)

    # Start the Bot
    updater.start_polling()
    logger.info("Bot started successfully!")

    # Run the bot until you press Ctrl-C
    updater.idle()

def error_handler(update: Update, context: CallbackContext):
    """Log Errors caused by Updates."""
    logger.warning(f'Update "{update}" caused error "{context.error}"')
