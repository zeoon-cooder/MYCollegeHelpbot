import os
import logging
import sys
from flask_app import app

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)

# Import flask app for use in the gunicorn workflow


# This is needed for the gunicorn workflow to find the app variable

def run_bot():
    """Run the Telegram bot."""
    from bot import setup_bot
    try:
        # Initialize and start the bot
        setup_bot()
    except Exception as e:
        logger.error(f"Error in bot thread: {e}")

def main():
    """Start the application based on the command-line argument or environment."""
    if len(sys.argv) > 1 and sys.argv[1] == "--web":
        # Running in web mode - don't do anything as gunicorn will handle it
        logger.info("Running in web mode, app will be started by gunicorn")
    else:
        # Default to running the bot
        logger.info("Starting Telegram bot")
        run_bot()

if __name__ == '__main__':
    main()
