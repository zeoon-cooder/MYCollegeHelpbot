from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import time

def create_loading_messages(subject_code):
    """Create a sequence of loading messages for animated display with color transitions."""
    # Define color transition patterns using emoji gradients
    color_transitions = [
        "🟩🟨🟧🟥",  # Green to yellow to orange to red
        "🟦🟪🟫⬜",  # Blue to purple to brown to white
        "⬜🟦🟩🟨",  # White to blue to green to yellow
        "🟪🟦⬜🟨",  # Purple to blue to white to yellow
        "🟥🟧🟨🟩"   # Red to orange to yellow to green
    ]
    
    # Using Unicode block elements for background
    backgrounds = [
        "░░░░░░░░",  # Light shade
        "▒▒▒▒▒▒▒▒",  # Medium shade
        "▓▓▓▓▓▓▓▓",  # Dark shade
        "█████████"   # Full block
    ]
    
    import random
    
    # Create sequence with varying colors and backgrounds
    loading_sequence = [
        f"{random.choice(color_transitions)}\n{backgrounds[0]}\n🔍 *Searching for {subject_code} resources...*",
        f"{random.choice(color_transitions)}\n{backgrounds[1]}\n🔎 *Fetching {subject_code} information...*",
        f"{random.choice(color_transitions)}\n{backgrounds[2]}\n📚 *Preparing {subject_code} resources...*",
        f"{random.choice(color_transitions)}\n{backgrounds[3]}\n✨ *Organizing {subject_code} materials...*"
    ]
    return loading_sequence

def format_resource_message(subject_code, subject_name, resources, searches_used, is_subscribed, upi_id):
    """Format the resource message with proper emoji and markdown and create inline keyboard."""
    
    # Emoji tooltips for different resource types
    notes_tooltips = [
        "📝 Take better notes with these!", 
        "✏️ Perfect study material!", 
        "📚 Study smart, not hard!", 
        "🧠 Knowledge at your fingertips!",
        "📓 Comprehensive class notes!"
    ]
    
    ppt_tooltips = [
        "🖼️ Visual learning rocks!", 
        "👨‍🏫 Straight from the professor!", 
        "📊 Slides to success!", 
        "💻 PowerPoint perfection!",
        "🎬 Presentation magic!"
    ]
    
    pyq_tooltips = [
        "📝 Practice makes perfect!", 
        "🔍 See what to expect!", 
        "❓ Test your knowledge!", 
        "🎯 Aim for top marks!",
        "⏳ Save study time!"
    ]
    
    # Import for random selection
    import random
    
    # Define color gradients for header and footer
    color_gradients = [
        "🟥🟧🟨🟩",  # Red to orange to yellow to green
        "🟩🟦🟪🟥",  # Green to blue to purple to red
        "🟦🟪🟥🟧",  # Blue to purple to red to orange
        "🟨🟩🟦🟪",  # Yellow to green to blue to purple
        "🟪🟦🟩🟨"   # Purple to blue to green to yellow
    ]
    
    # Choose random gradient for this message
    header_gradient = random.choice(color_gradients)
    footer_gradient = random.choice(color_gradients)
    
    # Create fancy background with dots
    dots = "•" * 20
    
    # Header with a more attractive design and color-shifting background
    message = (
        f"{header_gradient}\n"
        f"{dots}\n"
        f"🎓 *{subject_code}: {subject_name}*\n"
        f"{'✦'*15}\n"
        f"{dots}\n\n"
    )
    
    # Create a keyboard for quick copy buttons
    keyboard = []
    
    # Add resources by unit - improved formatting with color transitions
    for unit in range(1, 7):  # Units 1-6
        # Choose a random gradient for each unit to create a color-shifting effect
        unit_gradient = random.choice(color_gradients)
        wave_pattern = "\u25fa\u25fb\u25fc\u25fd" * 5  # Alternating square patterns
        
        message += f"{unit_gradient}\n"
        message += f"📌 *UNIT {unit}* 📌\n"
        message += f"{wave_pattern}\n"
        
        # Notes
        if 'notes' in resources[unit]:
            notes_link = resources[unit]['notes']
            message += f"📓 [Notes]({notes_link})\n"
            # Add copy button for notes with random tooltip
            notes_tooltip = random.choice(notes_tooltips)
            keyboard.append([
                InlineKeyboardButton(f"📓 Copy Unit {unit} Notes | {notes_tooltip}", url=notes_link)
            ])
        else:
            message += f"📓 Notes: Not available\n"
            
        # PPT
        if 'ppt' in resources[unit]:
            ppt_link = resources[unit]['ppt']
            message += f"📄 [PPT]({ppt_link})\n"
            # Add copy button for PPT with random tooltip
            ppt_tooltip = random.choice(ppt_tooltips)
            keyboard.append([
                InlineKeyboardButton(f"📄 Copy Unit {unit} PPT | {ppt_tooltip}", url=ppt_link)
            ])
        else:
            message += f"📄 PPT: Not available\n"
            
        # PYQ
        if 'pyq' in resources[unit]:
            pyq_link = resources[unit]['pyq']
            message += f"📋 [PYQs]({pyq_link})\n"
            # Add copy button for PYQ with random tooltip
            pyq_tooltip = random.choice(pyq_tooltips)
            keyboard.append([
                InlineKeyboardButton(f"📋 Copy Unit {unit} PYQs | {pyq_tooltip}", url=pyq_link)
            ])
        else:
            message += f"📋 PYQs: Not available\n"
            
        message += "\n"
    
    # Footer with subscription/usage information - enhanced design with color gradient
    if is_subscribed:
        message += (
            f"\n{dots}\n"
            f"{footer_gradient}\n"
            f"✅ *You have an active subscription* ✨\n"
            f"{footer_gradient}"
        )
    else:
        message += (
            f"\n{dots}\n"
            f"{footer_gradient}\n"
            f"🔢 *Searches Used:* {searches_used}/4\n"
            f"\n💰 *Upgrade to Premium*\n"
            f"- Price: ₹21 for 1 week of unlimited searches\n"
            f"- Payment: Send ₹21 to *{upi_id}* via UPI\n"
            f"- After payment, use /verify_payment with your UPI reference ID\n"
            f"{footer_gradient}"
        )
    
    # Create the reply markup if we have any buttons
    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    
    return message, reply_markup