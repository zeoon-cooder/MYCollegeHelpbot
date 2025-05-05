import re
import os
import logging
import sqlite3
from datetime import datetime
from telegram import Update, ParseMode, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove, CallbackQuery
from telegram.ext import CallbackContext, CallbackQueryHandler
from database import (
    get_user, create_user, increment_search_count, get_search_count,
    check_subscription, add_pending_payment, verify_payment, grant_access,
    add_resource, get_resources, get_user_stats, remove_resource, edit_resource, 
    delete_subject, DB_PATH, get_subscription_expiry, increment_subject_access,
    get_pending_verification_requests
)
from utils import format_resource_message, create_loading_messages

logger = logging.getLogger(__name__)

# Constants
# Try to get ADMIN_ID as integer, but fallback to string comparison if needed
ADMIN_ID = os.environ.get("ADMIN_ID", "0")
UPI_ID = os.environ.get("UPI_ID", "yourupi@paytm")
FREE_SEARCHES = 4

# Regular expression for subject codes (e.g., CSE211)
SUBJECT_CODE_PATTERN = re.compile(r'\b([A-Za-z]{2,3})(\d{3})\b')

def start_handler(update: Update, context: CallbackContext):
    """Handle the /start command."""
    user = update.effective_user
    telegram_id = user.id
    username = user.username or user.first_name
    
    # Create user if not exists
    if not get_user(telegram_id):
        create_user(telegram_id)
    
    message = (
        f"👋 Hello {username}!\n\n"
        f"Welcome to your University Resource Bot — your personal academic assistant.  \n"
        f"Simply mention any subject code like *CSE211* in your message, and I'll instantly fetch all available resources including:\n\n"
        f"📚 Notes  \n"
        f"📽️ PPTs  \n"
        f"❓ Previous Year Question Papers (PYQs)\n\n"
        f"🎁 You have *{FREE_SEARCHES} free searches* to explore.  \n"
        f"After that, unlock *unlimited access for 1 week* by paying just ₹21 via UPI.\n\n"
        f"Let's get started! Type your subject code now 👇"
    )
    
    update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

def help_handler(update: Update, context: CallbackContext):
    """Handle the /help command."""
    telegram_id = update.effective_user.id
    
    # Check subscription status
    is_subscribed = check_subscription(telegram_id)
    searches_used = get_search_count(telegram_id)
    
    subscription_status = (
        "✅ *Active Subscription*" if is_subscribed 
        else f"🔢 *Free Searches:* {searches_used}/{FREE_SEARCHES}"
    )
    
    # Basic commands for all users
    message = (
        f"🤖 *Educational Resources Bot Help*\n\n"
        f"*How to use:*\n"
        f"- Simply mention a subject code like *CSE211* in your message\n"
        f"- I'll show you available resources for that subject\n\n"
        f"*User Commands:*\n"
        f"- /start - Start the bot\n"
        f"- /help - Show this help message\n"
        f"- /my_history - Check your usage and subscription status\n"
        f"- /verify_payment <ref_id> - Submit payment for verification\n\n"
        f"*Your Status:*\n"
        f"{subscription_status}\n\n"
        f"*Subscription:*\n"
        f"- Price: ₹21 for 1 week of unlimited searches\n"
        f"- Payment: Send ₹21 to *{UPI_ID}* via UPI\n"
        f"- After payment, use /verify_payment with your UPI reference ID\n"
        f"- Example: `/verify_payment 12345678`"
    )
    
    # Add admin commands if this is an admin
    if str(telegram_id) == ADMIN_ID:
        admin_commands = (
            f"\n\n*Admin Commands:*\n"
            f"- /admin - Open the Admin Control Panel\n"
            f"- /verify <ref_id> - Verify a user's payment\n"
            f"- /grant_access <telegram_id> - Directly grant subscription access\n"
            f"- /add_resource - Start interactive resource addition flow\n"
            f"- /remove_resource <code> <unit> <type> - Remove a specific resource\n"
            f"- /edit_resource <code> <unit> <type> <new_link> - Update a resource link\n"
            f"- /delete_subject <code> - Delete all resources for a subject\n"
            f"- /upload_json - Bulk upload resources from a JSON file\n"
            f"- /stats - Show bot statistics"
        )
        message += admin_commands
    
    update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

def message_handler(update: Update, context: CallbackContext):
    """Handle incoming messages and detect subject codes or process pending inputs."""
    message_text = update.message.text
    telegram_id = update.effective_user.id
    
    # Check if this is a response to a pending subject name request (for admin)
    if str(telegram_id) == ADMIN_ID and 'pending_resource' in context.user_data:
        # Admin is providing a subject name for a new resource
        subject_name = message_text.strip()
        pending = context.user_data['pending_resource']
        
        # Add the resource with the provided subject name
        kwargs = {
            'subject_code': pending['subject_code'],
            'subject_name': subject_name,
            'unit_number': pending['unit_number']
        }
        
        if pending['resource_type'] == 'notes':
            kwargs['notes_link'] = pending['link']
        elif pending['resource_type'] == 'ppt':
            kwargs['ppt_link'] = pending['link']
        elif pending['resource_type'] == 'pyq':
            kwargs['pyq_link'] = pending['link']
        
        if add_resource(**kwargs):
            message = (
                f"✅ Resource added successfully!\n\n"
                f"- Subject Code: *{pending['subject_code']}*\n"
                f"- Subject Name: *{subject_name}*\n"
                f"- Unit: *{pending['unit_number']}*\n"
                f"- Type: *{pending['resource_type']}*\n"
                f"- Link: {pending['link']}"
            )
        else:
            message = "⚠️ Failed to add resource. Please try again."
        
        # Clear the pending state
        del context.user_data['pending_resource']
        
        update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
        return
        
    # Check if this is a response to delete subject confirmation (for admin)
    if str(telegram_id) == ADMIN_ID and 'delete_subject' in context.user_data:
        # Process delete subject confirmation
        process_delete_subject_confirmation(update, context)
        return
    
    # If not handling admin input, check for subject code
    match = SUBJECT_CODE_PATTERN.search(message_text)
    
    if not match:
        return
    
    subject_code = match.group(0).upper()
    
    # Create user if not exists
    if not get_user(telegram_id):
        create_user(telegram_id)
    
    # Check if user has an active subscription
    # The check_subscription function will automatically reset is_paid to 0 if subscription has expired
    is_subscribed = check_subscription(telegram_id)
    
    # Check if user has used all free searches
    searches_used = get_search_count(telegram_id)
    
    # Check user subscription status
    if not is_subscribed:
        # If user has a row in pending_payments with status='verified', it means
        # their subscription has expired rather than never having subscribed
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM pending_payments WHERE telegram_id = ? AND status = 'verified'",
            (telegram_id,)
        )
        payment_count = cursor.fetchone()[0]
        conn.close()
        
        had_subscription = payment_count > 0
        
        # If they've used all free searches, show payment prompt
        if searches_used >= FREE_SEARCHES:
            if had_subscription:
                # Subscription expired message
                message = (
                    f"⚠️ *Your subscription has expired*\n\n"
                    f"To continue accessing resources, please renew your subscription:\n"
                    f"- Send ₹21 to *{UPI_ID}* via UPI\n"
                    f"- After payment, use /verify_payment with your UPI reference ID\n"
                    f"- Example: `/verify_payment 12345678`\n\n"
                    f"Your subscription will be active for 1 week after verification."
                )
            else:
                # Free searches used up message
                message = (
                    f"⚠️ *You've used all your free searches*\n\n"
                    f"To continue accessing resources, please subscribe:\n"
                    f"- Send ₹21 to *{UPI_ID}* via UPI\n"
                    f"- After payment, use /verify_payment with your UPI reference ID\n"
                    f"- Example: `/verify_payment 12345678`\n\n"
                    f"Your subscription will be active for 1 week after verification."
                )
            update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
            return
    
    # Get resources for the subject code
    subject_name, resources = get_resources(subject_code)
    
    if not subject_name or not resources:
        update.message.reply_text(f"⚠️ No resources found for subject code: *{subject_code}*", parse_mode=ParseMode.MARKDOWN)
        return
        
    # Track subject access (only if resources found)
    increment_subject_access(subject_code)
    
    # Format the response message
    message, reply_markup = format_resource_message(subject_code, subject_name, resources, searches_used, is_subscribed, UPI_ID)
    
    # Increment search count if not subscribed
    if not is_subscribed:
        increment_search_count(telegram_id)
    
    # Get the loading message sequence
    loading_messages = create_loading_messages(subject_code)
    
    # Send the first loading message
    loading_msg = update.message.reply_text(loading_messages[0], parse_mode=ParseMode.MARKDOWN)
    
    # Store the data needed for the animation sequence
    context.user_data['edit_message_data'] = {
        'chat_id': update.effective_chat.id,
        'message_id': loading_msg.message_id,
        'loading_messages': loading_messages,
        'current_index': 0,
        'final_message': message,
        'reply_markup': reply_markup
    }
    
    # Show typing indicator for additional effect
    context.bot.send_chat_action(chat_id=telegram_id, action="typing")
    
    # Schedule the first animation update after a short delay (0.3 seconds)
    context.job_queue.run_once(
        animate_resource_loading, 
        0.3, 
        context=context.user_data['edit_message_data']
    )

def verify_payment_handler(update: Update, context: CallbackContext):
    """Handle the /verify_payment command."""
    telegram_id = update.effective_user.id
    
    # Check if reference ID is provided
    if not context.args or len(context.args) < 1:
        update.message.reply_text(
            "⚠️ Please provide your UPI reference ID.\n"
            "Example: `/verify_payment 12345678`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    reference_id = context.args[0]
    
    # Add pending payment
    if add_pending_payment(telegram_id, reference_id):
        message = (
            f"✅ Payment reference *{reference_id}* received!\n\n"
            f"Your payment will be verified by an admin shortly. "
            f"You'll receive a notification once it's confirmed."
        )
        
        # Notify admin about the new payment verification request
        admin_message = (
            f"🔔 *New Payment Verification Request*\n\n"
            f"- User ID: `{telegram_id}`\n"
            f"- Username: @{update.effective_user.username or 'N/A'}\n"
            f"- Reference ID: `{reference_id}`\n\n"
            f"To verify: `/verify {reference_id}`"
        )
        
        try:
            context.bot.send_message(
                chat_id=ADMIN_ID,
                text=admin_message,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Failed to notify admin: {e}")
    else:
        message = "⚠️ Failed to process your payment verification request. Please try again or contact support."
    
    update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

def admin_verify_payment_handler(update: Update, context: CallbackContext):
    """Handle the /verify command (admin only)."""
    telegram_id = update.effective_user.id
    
    # Check if the user is an admin
    if str(telegram_id) != ADMIN_ID:
        update.message.reply_text("⚠️ This command is for administrators only.")
        return
    
    # Check if reference ID is provided
    if not context.args or len(context.args) < 1:
        update.message.reply_text("⚠️ Please provide the UPI reference ID to verify.")
        return
    
    reference_id = context.args[0]
    
    # Verify the payment
    verified_telegram_id = verify_payment(reference_id)
    
    if verified_telegram_id:
        # Notify the admin
        admin_message = f"✅ Payment with reference ID *{reference_id}* has been verified successfully!"
        update.message.reply_text(admin_message, parse_mode=ParseMode.MARKDOWN)
        
        # Notify the user
        user_message = (
            f"🎉 Your payment with reference ID *{reference_id}* has been verified!\n\n"
            f"Your subscription is now active for 1 week. Enjoy unlimited searches!"
        )
        
        try:
            context.bot.send_message(
                chat_id=verified_telegram_id,
                text=user_message,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Failed to notify user {verified_telegram_id}: {e}")
    else:
        update.message.reply_text(f"⚠️ Failed to verify payment with reference ID *{reference_id}*.", parse_mode=ParseMode.MARKDOWN)

# Resource addition conversation states
# Used for the step-by-step resource addition flow
ADD_SUBJECT_CODE, ADD_SUBJECT_NAME, ADD_UNIT_NUMBER, ADD_RESOURCE_TYPE, ADD_RESOURCE_LINK, ADD_CONFIRMATION = range(6)

def add_resource_handler(update: Update, context: CallbackContext):
    """Handle the /add_resource command (admin only) with a step-by-step conversation flow."""
    telegram_id = update.effective_user.id
    
    # Check if the user is an admin
    if str(telegram_id) != ADMIN_ID:
        update.message.reply_text("⚠️ This command is for administrators only.")
        return
    
    # Check if there are any arguments - we'll ignore them in this new flow
    if context.args:
        update.message.reply_text(
            "💭 *Resource Addition - New Interactive Mode*\n\n"
            "I'll guide you through adding a resource step by step.\n"
            "No need to provide all arguments in a single command anymore!",
            parse_mode=ParseMode.MARKDOWN
        )
    
    # Initialize the resource collection in user_data
    context.user_data['add_resource'] = {}
    context.user_data['conversation_state'] = ADD_SUBJECT_CODE
    
    # Start the conversation by asking for subject code
    update.message.reply_text(
        "📚 *Add New Resource - Step 1/5*\n\n"
        "Please enter the *subject code* (e.g., CSE211):",
        parse_mode=ParseMode.MARKDOWN
    )
    return

def process_resource_conversation(update: Update, context: CallbackContext):
    """Process each step of the resource addition conversation."""
    telegram_id = update.effective_user.id
    message_text = update.message.text.strip()
    
    # Only admin can use this conversation
    if str(telegram_id) != ADMIN_ID:
        return
    
    # Check if we're in a resource addition conversation
    if 'conversation_state' not in context.user_data:
        return
    
    state = context.user_data['conversation_state']
    resource_data = context.user_data.get('add_resource', {})
    
    # Process based on current state
    if state == ADD_SUBJECT_CODE:
        # Process subject code
        subject_code = message_text.upper()
        
        # Validate subject code format (2-3 letters followed by 3 digits)
        if not re.match(r'^[A-Z]{2,3}\d{3}$', subject_code):
            update.message.reply_text(
                "⚠️ Invalid subject code format. Please enter a valid code like CSE211:",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Store subject code
        resource_data['subject_code'] = subject_code
        context.user_data['add_resource'] = resource_data
        
        # Check if subject already exists
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT subject_name FROM resources WHERE subject_code = ? LIMIT 1", (subject_code,))
        existing_subject = cursor.fetchone()
        conn.close()
        
        if existing_subject:
            # Subject exists, store the name and move to unit number
            resource_data['subject_name'] = existing_subject['subject_name']
            context.user_data['conversation_state'] = ADD_UNIT_NUMBER
            
            update.message.reply_text(
                f"📚 *Add New Resource - Step 2/5*\n\n"
                f"Subject *{subject_code}: {resource_data['subject_name']}* found in database.\n\n"
                f"Please enter the *unit number* (1-6):",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            # Subject doesn't exist, ask for subject name
            context.user_data['conversation_state'] = ADD_SUBJECT_NAME
            
            update.message.reply_text(
                f"🌟 *Add New Resource - Step 2/5*\n\n"
                f"Subject code *{subject_code}* is not in the database.\n\n"
                f"Please enter the *full subject name*:",
                parse_mode=ParseMode.MARKDOWN
            )
    
    elif state == ADD_SUBJECT_NAME:
        # Process subject name
        subject_name = message_text
        
        # Validate subject name length
        if len(subject_name) < 3 or len(subject_name) > 100:
            update.message.reply_text(
                "⚠️ Subject name is too short or too long. Please enter a valid name (3-100 characters):",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Store subject name
        resource_data['subject_name'] = subject_name
        context.user_data['add_resource'] = resource_data
        context.user_data['conversation_state'] = ADD_UNIT_NUMBER
        
        update.message.reply_text(
            f"📚 *Add New Resource - Step 3/5*\n\n"
            f"Subject name: *{subject_name}*\n\n"
            f"Please enter the *unit number* (1-6):",
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif state == ADD_UNIT_NUMBER:
        # Process unit number
        try:
            unit_number = int(message_text)
            
            # Validate unit number range
            if unit_number < 1 or unit_number > 6:
                update.message.reply_text(
                    "⚠️ Unit number must be between 1 and 6. Please enter a valid unit number:",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            
            # Store unit number
            resource_data['unit_number'] = unit_number
            context.user_data['add_resource'] = resource_data
            context.user_data['conversation_state'] = ADD_RESOURCE_TYPE
            
            # Create a keyboard for resource type selection
            keyboard = [
                ["notes", "ppt", "pyq"]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
            
            update.message.reply_text(
                f"📚 *Add New Resource - Step 4/5*\n\n"
                f"Unit number: *{unit_number}*\n\n"
                f"Please select the *resource type* (notes, ppt, pyq):",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
        except ValueError:
            update.message.reply_text(
                "⚠️ Please enter a valid number for the unit (1-6):",
                parse_mode=ParseMode.MARKDOWN
            )
    
    elif state == ADD_RESOURCE_TYPE:
        # Process resource type
        resource_type = message_text.lower()
        
        # Validate resource type
        if resource_type not in ['notes', 'ppt', 'pyq']:
            # Create a keyboard for resource type selection for retry
            keyboard = [
                ["notes", "ppt", "pyq"]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
            
            update.message.reply_text(
                "⚠️ Invalid resource type. Please select one of: notes, ppt, or pyq:",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
            return
        
        # Store resource type
        resource_data['resource_type'] = resource_type
        context.user_data['add_resource'] = resource_data
        context.user_data['conversation_state'] = ADD_RESOURCE_LINK
        
        # Remove custom keyboard
        reply_markup = ReplyKeyboardRemove()
        
        update.message.reply_text(
            f"📚 *Add New Resource - Step 5/5*\n\n"
            f"Resource type: *{resource_type}*\n\n"
            f"Please enter the resource *link* (must start with http:// or https://):",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
    
    elif state == ADD_RESOURCE_LINK:
        # Process resource link
        link = message_text.strip()
        
        # Validate link format
        if not link.startswith('http'):
            update.message.reply_text(
                "⚠️ Link must start with http:// or https://. Please enter a valid link:",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Store link
        resource_data['link'] = link
        context.user_data['add_resource'] = resource_data
        context.user_data['conversation_state'] = ADD_CONFIRMATION
        
        # Create a confirmation keyboard
        keyboard = [
            ["✅ Confirm", "❌ Cancel"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        
        # Show summary for confirmation
        update.message.reply_text(
            f"📝 *Resource Addition - Confirmation*\n\n"
            f"Please review the resource details:\n\n"
            f"- Subject Code: *{resource_data['subject_code']}*\n"
            f"- Subject Name: *{resource_data['subject_name']}*\n"
            f"- Unit Number: *{resource_data['unit_number']}*\n"
            f"- Resource Type: *{resource_data['resource_type']}*\n"
            f"- Link: {resource_data['link']}\n\n"
            f"Is this correct?",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
    
    elif state == ADD_CONFIRMATION:
        # Process confirmation
        confirmation = message_text.strip().lower()
        
        # Remove custom keyboard
        reply_markup = ReplyKeyboardRemove()
        
        if "confirm" in confirmation or "✅" in confirmation:
            # Add the resource to the database
            subject_code = resource_data['subject_code']
            subject_name = resource_data['subject_name']
            unit_number = resource_data['unit_number']
            resource_type = resource_data['resource_type']
            link = resource_data['link']
            
            # Prepare kwargs for add_resource
            kwargs = {
                'subject_code': subject_code,
                'subject_name': subject_name,
                'unit_number': unit_number
            }
            
            if resource_type == 'notes':
                kwargs['notes_link'] = link
            elif resource_type == 'ppt':
                kwargs['ppt_link'] = link
            elif resource_type == 'pyq':
                kwargs['pyq_link'] = link
            
            if add_resource(**kwargs):
                update.message.reply_text(
                    f"✨ *Resource added successfully!*\n\n"
                    f"- Subject: *{subject_code}: {subject_name}*\n"
                    f"- Unit: *{unit_number}*\n"
                    f"- Type: *{resource_type}*\n\n"
                    f"Use /add_resource again to add another resource.",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=reply_markup
                )
            else:
                update.message.reply_text(
                    "⚠️ Failed to add resource to the database. Please try again later.",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=reply_markup
                )
        else:
            update.message.reply_text(
                "\ud83d\udeab Resource addition canceled.\n\nUse /add_resource to start again.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
        
        # Clear conversation state
        if 'conversation_state' in context.user_data:
            del context.user_data['conversation_state']
        if 'add_resource' in context.user_data:
            del context.user_data['add_resource']

def grant_access_handler(update: Update, context: CallbackContext):
    """Handle the /grant_access command (admin only)."""
    telegram_id = update.effective_user.id
    
    # Check if the user is an admin
    if str(telegram_id) != ADMIN_ID:
        update.message.reply_text("⚠️ This command is for administrators only.")
        return
    
    # Check if Telegram ID is provided
    if not context.args or len(context.args) < 1:
        update.message.reply_text(
            "⚠️ Please provide the user's Telegram ID.\n"
            "Example: `/grant_access 123456789`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    try:
        user_telegram_id = int(context.args[0])
    except ValueError:
        update.message.reply_text("⚠️ Telegram ID must be a number.")
        return
    
    # Grant access to the user
    if grant_access(user_telegram_id):
        # Notify the admin
        admin_message = f"✅ Access granted to user with Telegram ID *{user_telegram_id}* successfully!"
        update.message.reply_text(admin_message, parse_mode=ParseMode.MARKDOWN)
        
        # Notify the user
        user_message = (
            f"🎉 Your subscription has been activated!\n\n"
            f"Your subscription is now active for 1 week. Enjoy unlimited searches!"
        )
        
        try:
            context.bot.send_message(
                chat_id=user_telegram_id,
                text=user_message,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Failed to notify user {user_telegram_id}: {e}")
    else:
        update.message.reply_text(f"⚠️ Failed to grant access to user with Telegram ID *{user_telegram_id}*.", parse_mode=ParseMode.MARKDOWN)

def animate_resource_loading(context: CallbackContext):
    """Job callback to animate resource loading with a sequence of messages."""
    job_data = context.job.context
    try:
        current_index = job_data['current_index']
        loading_messages = job_data['loading_messages']
        
        # If we haven't shown all loading messages yet, show the next one
        if current_index < len(loading_messages) - 1:
            current_index += 1
            job_data['current_index'] = current_index
            
            # Edit the message to show the next loading message
            context.bot.edit_message_text(
                chat_id=job_data['chat_id'],
                message_id=job_data['message_id'],
                text=loading_messages[current_index],
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Schedule the next animation update
            context.job_queue.run_once(
                animate_resource_loading, 
                0.5,  # Slightly longer delay for reading
                context=job_data
            )
        else:
            # We've shown all loading messages, now show the actual resources
            context.bot.edit_message_text(
                chat_id=job_data['chat_id'],
                message_id=job_data['message_id'],
                text=job_data['final_message'],
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True,
                reply_markup=job_data['reply_markup']
            )
    except Exception as e:
        logger.error(f"Failed during resource loading animation: {e}")

def button_callback_handler(update: Update, context: CallbackContext):
    """Handle button callbacks from inline keyboards."""
    query = update.callback_query
    data = query.data
    telegram_id = query.from_user.id
    
    # Always answer the callback query to remove the loading state
    query.answer()
    
    # Handle admin panel buttons (only for admin)
    if data.startswith("admin_") and str(telegram_id) == ADMIN_ID:
        handle_admin_button(query, context)
        return
    
    # Handle copy buttons for resource links
    if data.startswith("copy_"):
        # The format is "copy_<link>"
        link = data[5:]  # Remove the "copy_" prefix to get the actual link
        query.message.reply_text(
            f"🔗 *Here's your link:*\n{link}", 
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
        return
    
    # Handle menu navigation buttons
    if data == "back_to_admin":
        # Re-send the admin panel
        # Use a separate function to avoid code duplication
        admin_panel_message(query.message, context)
        return

def handle_admin_button(query: CallbackQuery, context: CallbackContext):
    """Handle admin panel button clicks."""
    data = query.data
    message = query.message
    
    # Handle different admin panel sections
    if data == "admin_verify":
        # Show verification requests panel
        show_verification_panel(message, context)
    
    elif data == "admin_resources":
        # Show resource management panel
        show_resource_panel(message, context)
    
    elif data == "admin_users":
        # Show user management panel
        show_user_panel(message, context)
    
    elif data == "admin_stats":
        # Show system stats panel
        show_stats_panel(message, context)
    
    # Handle specific action buttons
    elif data.startswith("approve_payment_"):
        # Extract reference ID and approve payment
        ref_id = data[16:]  # Remove "approve_payment_" prefix
        handle_payment_approval(ref_id, message, context)
    
    elif data.startswith("open_add_resource"):
        # Prompt admin to use /add_resource command
        message.reply_text(
            "📝 Please use the `/add_resource` command to start the interactive resource addition process.",
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif data.startswith("open_grant_access"):
        # Prompt admin to use /grant_access command
        message.reply_text(
            "🔑 Please use the `/grant_access <telegram_id>` command to grant subscription access.",
            parse_mode=ParseMode.MARKDOWN
        )

def show_verification_panel(message, context):
    """Show the verification requests panel."""
    # Get pending verification requests
    pending_requests = get_pending_verification_requests()
    pending_count = len(pending_requests)
    
    # Create verification panel message
    header = "💳 *Verification Requests*\n\n"
    
    if pending_count > 0:
        content = f"Found {pending_count} pending payment verification{'s' if pending_count > 1 else ''}:\n\n"
        
        # List all pending requests with approve buttons
        for i, request in enumerate(pending_requests[:5]):  # Show up to 5 requests
            telegram_id = request['telegram_id']
            ref_id = request['reference_id']
            request_time = request['request_time']
            
            content += f"{i+1}. User ID: `{telegram_id}`\n"
            content += f"   Reference: `{ref_id}`\n"
            content += f"   Time: {request_time}\n\n"
        
        if pending_count > 5:
            content += f"_...and {pending_count - 5} more pending requests._\n\n"
    else:
        content = "No pending verification requests.\n\n"
    
    # Create keyboard with approve buttons for each request
    keyboard = []
    
    if pending_count > 0:
        # Add approval buttons for each request (up to 5)
        for i, request in enumerate(pending_requests[:5]):
            keyboard.append([InlineKeyboardButton(
                f"Approve #{i+1}: {request['reference_id']}", 
                callback_data=f"approve_payment_{request['reference_id']}"
            )])
    
    # Add back button
    keyboard.append([InlineKeyboardButton("« Back to Menu", callback_data="back_to_admin")])
    
    # Construct reply markup
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send or edit message
    message.edit_text(
        header + content,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

def show_resource_panel(message, context):
    """Show the resource management panel."""
    # Get resource statistics
    stats = get_user_stats()
    
    # Create resource panel message
    header = "📚 *Resource Management*\n\n"
    content = f"Total Resources: {stats['total_resources']} | Subjects: {stats['subject_count']}\n\n"
    content += "Use these commands to manage resources:\n\n"
    content += "• `/add_resource` - Add new resource\n"
    content += "• `/edit_resource <code> <unit> <type> <new_link>` - Edit link\n"
    content += "• `/remove_resource <code> <unit> <type>` - Remove resource\n"
    content += "• `/delete_subject <code>` - Delete subject\n"
    content += "• `/upload_json` - Bulk upload resources\n"
    
    # Create keyboard with resource management buttons
    keyboard = [
        [InlineKeyboardButton("Add Resource", callback_data="open_add_resource")],
        [InlineKeyboardButton("Upload JSON File", callback_data="open_upload_json")],
        [InlineKeyboardButton("« Back to Menu", callback_data="back_to_admin")]
    ]
    
    # Construct reply markup
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send or edit message
    message.edit_text(
        header + content,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

def show_user_panel(message, context):
    """Show the user management panel."""
    # Get user statistics
    stats = get_user_stats()
    
    # Create user panel message
    header = "👤 *User Management*\n\n"
    content = f"Total Users: {stats['total_users']} | Active Subscribers: {stats['active_subscribers']}\n\n"
    content += "Use these commands to manage users:\n\n"
    content += "• `/grant_access <telegram_id>` - Give subscription\n"
    content += "• `/stats` - View detailed statistics\n"
    
    # Create keyboard with user management buttons
    keyboard = [
        [InlineKeyboardButton("Grant Access", callback_data="open_grant_access")],
        [InlineKeyboardButton("View Statistics", callback_data="admin_stats")],
        [InlineKeyboardButton("« Back to Menu", callback_data="back_to_admin")]
    ]
    
    # Construct reply markup
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send or edit message
    message.edit_text(
        header + content,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

def show_stats_panel(message, context):
    """Show the system statistics panel."""
    # Get system statistics
    stats = get_user_stats()
    
    # Create stats panel message
    header = "📊 *System Status*\n\n"
    content = f"Most Accessed: {stats.get('most_accessed_subject', 'None')}\n"
    content += f"Verified Payments: {stats['total_payments']}\n"
    content += f"Total Users: {stats['total_users']}\n"
    content += f"Active Subscribers: {stats['active_subscribers']}\n"
    content += f"Pending Payments: {stats['pending_payments']}\n"
    content += f"Total Resources: {stats['total_resources']}\n"
    content += f"Subject Count: {stats['subject_count']}\n"
    content += f"Current Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    
    # Create keyboard with back button
    keyboard = [
        [InlineKeyboardButton("« Back to Menu", callback_data="back_to_admin")]
    ]
    
    # Construct reply markup
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send or edit message
    message.edit_text(
        header + content,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

def handle_payment_approval(ref_id, message, context):
    """Handle payment approval from admin panel."""
    # Verify the payment
    verified_telegram_id = verify_payment(ref_id)
    
    if verified_telegram_id:
        # Notify admin of successful verification
        notification = f"✅ Payment with reference ID *{ref_id}* has been verified successfully!"
        message.reply_text(notification, parse_mode=ParseMode.MARKDOWN)
        
        # Notify the user
        user_message = (
            f"🎉 Your payment with reference ID *{ref_id}* has been verified!\n\n"
            f"Your subscription is now active for 1 week. Enjoy unlimited searches!"
        )
        
        try:
            context.bot.send_message(
                chat_id=verified_telegram_id,
                text=user_message,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Failed to notify user {verified_telegram_id}: {e}")
        
        # Refresh the verification panel
        show_verification_panel(message, context)
    else:
        # Notify admin of failed verification
        message.reply_text(
            f"⚠️ Failed to verify payment with reference ID *{ref_id}*.\n"
            f"The payment may have already been verified or doesn't exist.",
            parse_mode=ParseMode.MARKDOWN
        )

def admin_panel_message(message, context):
    """Generate and send/edit the admin panel message."""
    # Get pending verification requests
    pending_requests = get_pending_verification_requests()
    pending_count = len(pending_requests)
    
    # Get current statistics
    stats = get_user_stats()
    if not stats:
        message.reply_text("⚠️ Failed to retrieve statistics.")
        return
    
    # Create a more visual header for the admin panel
    color_gradient = "🟥🟧🟨🟩"
    header_text = f"{color_gradient} *ADMIN CONTROL PANEL* {color_gradient[-1::-1]}\n"
    header_text += "Welcome, Admin! Manage the bot with ease.\n\n"
    
    # Create message with system overview
    msg_text = header_text
    
    # System Overview
    msg_text += "📊 *System Overview*\n"
    msg_text += f"• Total Users: {stats['total_users']} | Active Subscribers: {stats['active_subscribers']}\n"
    msg_text += f"• Verified Payments: {stats['total_payments']} | Pending Requests: {pending_count}\n"
    msg_text += f"• Most Accessed Resource: {stats.get('most_accessed_subject', 'None')}\n"
    msg_text += f"• Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    
    # Control Menu Description
    msg_text += "🛠️ *Control Menu*\n"
    msg_text += "[ Verification Requests ] [ Resource Management ]\n"
    msg_text += "[ User Management ]      [ System Stats ]\n\n"
    msg_text += "ℹ️ Select an option below to proceed."
    
    # Create the inline keyboard with buttons
    keyboard = [
        [
            InlineKeyboardButton("📳 Verification", callback_data="admin_verify"),
            InlineKeyboardButton("📚 Resources", callback_data="admin_resources")
        ],
        [
            InlineKeyboardButton("👤 Users", callback_data="admin_users"),
            InlineKeyboardButton("📊 Stats", callback_data="admin_stats")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Check if this is a new message or an edit
    if hasattr(message, 'edit_text'):  # This is a Message object from a callback query
        # Edit the existing message
        message.edit_text(
            msg_text, 
            reply_markup=reply_markup, 
            parse_mode=ParseMode.MARKDOWN
        )
    else:  # This is a fresh command, use reply_text
        message.reply_text(
            msg_text, 
            reply_markup=reply_markup, 
            parse_mode=ParseMode.MARKDOWN
        )

def my_history_handler(update: Update, context: CallbackContext):
    """Handle the /my_history command to show user's usage and subscription status."""
    telegram_id = update.effective_user.id
    username = update.effective_user.username or telegram_id
    
    # Check if user exists in database
    user = get_user(telegram_id)
    if not user:
        # User doesn't exist in the database
        message = (
            f"👋 Hello @{username}!\n\n"
            f"✅ You haven't made any searches yet. You have *{FREE_SEARCHES}* free searches available.\n"
            f"📅 Subscription: Not active. Upgrade for unlimited access."
        )
        update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
        return
    
    # Get current search count
    searches_used = get_search_count(telegram_id)
    
    # Check subscription status
    is_subscribed = check_subscription(telegram_id)
    
    # Format searches used message
    if is_subscribed:
        searches_message = f"✅ You have *unlimited* searches (subscription active).\n"
    else:
        searches_remaining = max(0, FREE_SEARCHES - searches_used)
        searches_message = f"✅ You've used *{searches_used}/{FREE_SEARCHES}* free searches.\n"
    
    # Format subscription message
    if is_subscribed:
        # Get subscription expiry date
        expiry_date = get_subscription_expiry(telegram_id)
        if expiry_date:
            # Format date as DD-MMM-YYYY
            formatted_date = expiry_date.strftime("%d-%b-%Y")
            subscription_message = f"📅 Subscription: Active till *{formatted_date}*"
        else:
            # This shouldn't happen, but just in case
            subscription_message = f"📅 Subscription: Active"
    else:
        subscription_message = f"📅 Subscription: Not active. Upgrade for unlimited access."
    
    # Compile full message
    message = (
        f"👋 Hello @{username}!\n\n"
        f"{searches_message}"
        f"{subscription_message}"
    )
    
    update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

def remove_resource_handler(update: Update, context: CallbackContext):
    """Handle the /remove_resource command (admin only)."""
    telegram_id = update.effective_user.id
    
    # Check if the user is an admin
    if str(telegram_id) != ADMIN_ID:
        update.message.reply_text("⚠️ This command is for administrators only.")
        return
    
    # Check if required arguments are provided
    if not context.args or len(context.args) < 3:
        update.message.reply_text(
            "⚠️ Please provide all required information.\n"
            "Format: `/remove_resource <code> <unit> <type>`\n"
            "Example: `/remove_resource CSE211 1 notes`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Extract arguments
    subject_code = context.args[0].upper()
    try:
        unit_number = int(context.args[1])
        resource_type = context.args[2].lower()
    except (ValueError, IndexError):
        update.message.reply_text(
            "⚠️ Invalid format. Please use the following format:\n"
            "`/remove_resource <code> <unit> <type>`\n"
            "Example: `/remove_resource CSE211 1 notes`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Validate unit number
    if unit_number < 1 or unit_number > 6:
        update.message.reply_text("⚠️ Unit number must be between 1 and 6.")
        return
    
    # Validate resource type
    if resource_type not in ['notes', 'ppt', 'pyq']:
        update.message.reply_text(
            "⚠️ Invalid resource type. Use 'notes', 'ppt', or 'pyq'.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Remove the resource
    success, message_text = remove_resource(subject_code, unit_number, resource_type)
    
    if success:
        message = (
            f"✅ Resource removed successfully!\n\n"
            f"- Subject Code: *{subject_code}*\n"
            f"- Unit: *{unit_number}*\n"
            f"- Type: *{resource_type}*\n"
        )
    else:
        message = f"⚠️ Failed to remove resource: {message_text}"
    
    update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

def edit_resource_handler(update: Update, context: CallbackContext):
    """Handle the /edit_resource command (admin only)."""
    telegram_id = update.effective_user.id
    
    # Check if the user is an admin
    if str(telegram_id) != ADMIN_ID:
        update.message.reply_text("⚠️ This command is for administrators only.")
        return
    
    # Check if required arguments are provided
    if not context.args or len(context.args) < 4:
        update.message.reply_text(
            "⚠️ Please provide all required information.\n"
            "Format: `/edit_resource <code> <unit> <type> <new_link>`\n"
            "Example: `/edit_resource CSE211 1 notes https://example.com/new-notes`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Extract arguments
    subject_code = context.args[0].upper()
    try:
        unit_number = int(context.args[1])
        resource_type = context.args[2].lower()
        new_link = context.args[3]
    except (ValueError, IndexError):
        update.message.reply_text(
            "⚠️ Invalid format. Please use the following format:\n"
            "`/edit_resource <code> <unit> <type> <new_link>`\n"
            "Example: `/edit_resource CSE211 1 notes https://example.com/new-notes`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Validate unit number
    if unit_number < 1 or unit_number > 6:
        update.message.reply_text("⚠️ Unit number must be between 1 and 6.")
        return
    
    # Validate resource type
    if resource_type not in ['notes', 'ppt', 'pyq']:
        update.message.reply_text(
            "⚠️ Invalid resource type. Use 'notes', 'ppt', or 'pyq'.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Check if link is valid
    if not new_link.startswith('http'):
        update.message.reply_text("⚠️ Link must start with http:// or https://")
        return
    
    # Edit the resource
    success, message_text = edit_resource(subject_code, unit_number, resource_type, new_link)
    
    if success:
        message = (
            f"✅ Resource updated successfully!\n\n"
            f"- Subject Code: *{subject_code}*\n"
            f"- Unit: *{unit_number}*\n"
            f"- Type: *{resource_type}*\n"
            f"- New Link: {new_link}"
        )
    else:
        message = f"⚠️ Failed to update resource: {message_text}"
    
    update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)

def delete_subject_handler(update: Update, context: CallbackContext):
    """Handle the /delete_subject command (admin only)."""
    telegram_id = update.effective_user.id
    
    # Check if the user is an admin
    if str(telegram_id) != ADMIN_ID:
        update.message.reply_text("⚠️ This command is for administrators only.")
        return
    
    # Check if subject code is provided
    if not context.args or len(context.args) < 1:
        update.message.reply_text(
            "⚠️ Please provide a subject code.\n"
            "Format: `/delete_subject <code>`\n"
            "Example: `/delete_subject CSE211`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Extract argument
    subject_code = context.args[0].upper()
    
    # Create a confirmation keyboard
    keyboard = [
        ["✅ Confirm Delete", "❌ Cancel"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    # Ask for confirmation before deleting
    context.user_data['delete_subject'] = {
        'subject_code': subject_code
    }
    
    message = (
        f"⚠️ *WARNING: You are about to delete all resources for {subject_code}*\n\n"
        f"This action cannot be undone. Are you sure you want to continue?"
    )
    
    update.message.reply_text(
        message, 
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

def process_delete_subject_confirmation(update: Update, context: CallbackContext):
    """Process confirmation for subject deletion."""
    telegram_id = update.effective_user.id
    message_text = update.message.text
    
    # Only admin can use this
    if str(telegram_id) != ADMIN_ID:
        return
    
    # Check if we're awaiting confirmation
    if 'delete_subject' not in context.user_data:
        return
    
    # Remove custom keyboard
    reply_markup = ReplyKeyboardRemove()
    
    if "✅" in message_text or "Confirm" in message_text:
        # Confirmed - delete the subject
        subject_code = context.user_data['delete_subject']['subject_code']
        success, message_text = delete_subject(subject_code)
        
        if success:
            message = f"✅ {message_text}"
        else:
            message = f"⚠️ Failed to delete subject: {message_text}"
    else:
        # Cancelled
        message = "🚫 Subject deletion cancelled."
    
    # Clear the confirmation state
    del context.user_data['delete_subject']
    
    update.message.reply_text(
        message, 
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

def upload_json_handler(update: Update, context: CallbackContext):
    """Handle the /upload_json command to bulk upload resources via a JSON file (admin only)."""
    telegram_id = update.effective_user.id
    
    # Check if the user is an admin
    if str(telegram_id) != ADMIN_ID:
        update.message.reply_text("⚠️ This command is for administrators only.")
        return
    
    # Store state to listen for file upload
    context.user_data['awaiting_json'] = True
    
    # Provide instructions for JSON format
    instructions = (
        f"📚 *Bulk Resource Upload*\n\n"
        f"Please upload a JSON file with the following format:\n\n"
        "```\n"
        "[\n"
        "  {\n"
        "    \"subject_code\": \"CSE211\",\n"
        "    \"subject_name\": \"Data Structures\",\n"
        "    \"unit\": 1,\n"
        "    \"type\": \"notes\",\n"
        "    \"link\": \"https://example.com/notes\"\n"
        "  },\n"
        "  {\n"
        "    \"subject_code\": \"CSE211\",\n"
        "    \"subject_name\": \"Data Structures\",\n"
        "    \"unit\": 1,\n"
        "    \"type\": \"ppt\",\n"
        "    \"link\": \"https://example.com/ppt\"\n"
        "  }\n"
        "]\n"
        "```\n\n"
        f"Each object must contain:\n"
        f"- `subject_code`: Course code (e.g., CSE211)\n"
        f"- `subject_name`: Full name of the subject\n"
        f"- `unit`: Unit number (1-6)\n"
        f"- `type`: Resource type (must be one of: notes, ppt, pyq)\n"
        f"- `link`: URL to the resource (must start with http:// or https://)\n\n"
        f"Now, please upload your JSON file."
    )
    
    update.message.reply_text(instructions, parse_mode=ParseMode.MARKDOWN)

def process_json_upload(update: Update, context: CallbackContext):
    """Process JSON file upload for bulk resource addition."""
    telegram_id = update.effective_user.id
    
    # Only admin can use this function
    if str(telegram_id) != ADMIN_ID:
        return
    
    # Check if we're expecting a JSON upload
    if not context.user_data.get('awaiting_json', False):
        return
    
    # Reset the awaiting flag
    context.user_data['awaiting_json'] = False
    
    # Get the file
    document = update.message.document
    if not document or not document.file_name.lower().endswith('.json'):
        update.message.reply_text(
            "⚠️ Please upload a JSON file with .json extension.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    try:
        # Download the file
        file = context.bot.get_file(document.file_id)
        json_file = file.download_as_bytearray()
        
        # Parse the JSON
        import json
        resources = json.loads(json_file.decode('utf-8'))
        
        # Validate the JSON format
        if not isinstance(resources, list):
            update.message.reply_text(
                "⚠️ Invalid JSON format. The file must contain a list of resource objects.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Keep track of processed resources and errors
        successful_resources = 0
        failed_resources = 0
        subjects_added = set()
        error_messages = []
        
        # Process each resource
        for i, resource in enumerate(resources):
            # Check for required fields
            if not all(key in resource for key in ['subject_code', 'subject_name', 'unit', 'type', 'link']):
                error_message = f"Resource #{i+1}: Missing required fields. Each resource must contain subject_code, subject_name, unit, type, and link."
                error_messages.append(error_message)
                failed_resources += 1
                continue
            
            # Validate fields
            subject_code = resource['subject_code'].upper()
            subject_name = resource['subject_name']
            
            # Validate unit
            try:
                unit = int(resource['unit'])
                if unit < 1 or unit > 6:
                    error_message = f"Resource #{i+1}: Unit number must be between 1 and 6."
                    error_messages.append(error_message)
                    failed_resources += 1
                    continue
            except (ValueError, TypeError):
                error_message = f"Resource #{i+1}: Unit must be a number between 1 and 6."
                error_messages.append(error_message)
                failed_resources += 1
                continue
            
            # Validate resource type
            resource_type = resource['type'].lower()
            if resource_type not in ['notes', 'ppt', 'pyq']:
                error_message = f"Resource #{i+1}: Resource type must be one of: notes, ppt, pyq."
                error_messages.append(error_message)
                failed_resources += 1
                continue
            
            # Validate link
            link = resource['link']
            if not link.startswith('http'):
                error_message = f"Resource #{i+1}: Link must start with http:// or https://."
                error_messages.append(error_message)
                failed_resources += 1
                continue
            
            # Prepare arguments for add_resource function
            kwargs = {
                'subject_code': subject_code,
                'subject_name': subject_name,
                'unit_number': unit
            }
            
            if resource_type == 'notes':
                kwargs['notes_link'] = link
            elif resource_type == 'ppt':
                kwargs['ppt_link'] = link
            elif resource_type == 'pyq':
                kwargs['pyq_link'] = link
            
            # Add the resource to the database
            if add_resource(**kwargs):
                successful_resources += 1
                subjects_added.add(subject_code)
            else:
                error_message = f"Resource #{i+1}: Failed to add resource to database."
                error_messages.append(error_message)
                failed_resources += 1
        
        # Format response message
        if successful_resources > 0:
            sorted_subjects = sorted(list(subjects_added))
            success_message = f"✅ Successfully uploaded *{successful_resources}* resources for subject(s): *{', '.join(sorted_subjects)}*."
            
            if failed_resources > 0:
                error_summary = f"\n\n⚠️ *{failed_resources} resources could not be added due to errors:*"
                # Show up to 5 error messages to avoid message length limits
                if len(error_messages) > 5:
                    error_detail = "\n- " + "\n- ".join(error_messages[:5]) + f"\n- ... and {len(error_messages) - 5} more errors."
                else:
                    error_detail = "\n- " + "\n- ".join(error_messages)
                
                message = success_message + error_summary + error_detail
            else:
                message = success_message
        else:
            message = "⚠️ Failed to add any resources. Please check the following errors:\n\n"
            message += "- " + "\n- ".join(error_messages[:10])
            if len(error_messages) > 10:
                message += f"\n- ... and {len(error_messages) - 10} more errors."
        
        update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
        
    except json.JSONDecodeError:
        update.message.reply_text(
            "⚠️ Invalid JSON format. Please check your file and try again.",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Error processing JSON upload: {e}")
        update.message.reply_text(
            f"⚠️ Error processing JSON file: {str(e)}",
            parse_mode=ParseMode.MARKDOWN
        )

def admin_panel_handler(update: Update, context: CallbackContext):
    """Handle the /admin command to show an admin panel with options."""
    telegram_id = update.effective_user.id
    
    # Check if the user is an admin
    if str(telegram_id) != ADMIN_ID:
        update.message.reply_text("⚠️ This command is for administrators only.")
        return
    
    # Use the centralized admin panel message function
    admin_panel_message(update.message, context)

def stats_handler(update: Update, context: CallbackContext):
    """Handle the /stats command (admin only)."""
    telegram_id = update.effective_user.id
    
    # Check if the user is an admin
    if str(telegram_id) != ADMIN_ID:
        update.message.reply_text("⚠️ This command is for administrators only.")
        return
    
    # Get statistics
    stats = get_user_stats()
    
    if not stats:
        update.message.reply_text("⚠️ Failed to retrieve statistics.")
        return
    
    # Get the most accessed subject
    most_accessed = stats.get('most_accessed_subject', 'None')
    
    # Format the simplified statistics message as requested
    simple_message = (
        f"👥 Total Users: {stats['total_users']}  \n"
        f"🔓 Active Subscribers: {stats['active_subscribers']}  \n"
        f"📦 Most Accessed Subject: {most_accessed}"
    )
    
    update.message.reply_text(simple_message, parse_mode=ParseMode.MARKDOWN)
