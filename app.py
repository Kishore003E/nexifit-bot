import os
import re
import threading
from datetime import datetime, timedelta
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
from typing import Annotated
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, AnyMessage, SystemMessage
from apscheduler.schedulers.background import BackgroundScheduler

# Import database functions
from database import (
    is_user_authorized, is_admin, log_auth_attempt,
    add_user, remove_user, reactivate_user, list_all_users,
    get_user_info, clean_expired_users,
    # Mental health tips functions
    add_mental_health_tip, get_all_mental_health_tips, deactivate_tip, activate_tip,
    get_next_tip_for_user, log_tip_sent, set_user_tip_preference, 
    get_user_tip_preference, get_users_for_daily_tips, get_user_tip_stats,
    get_global_tip_stats, get_tip_by_id,
    # Workout tracking functions
    log_workout_completion, get_weekly_progress, get_users_for_weekly_report
)

# -------------------------
# Twilio credentials
# -------------------------
TWILIO_SID = os.environ.get("TWILIO_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.environ.get("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")
ADMIN_CONTACT = os.environ.get("ADMIN_CONTACT", "admin@nexifit.com")

client = Client(TWILIO_SID, TWILIO_AUTH_TOKEN)

# -------------------------
# Initialize Gemini
# -------------------------
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
llm = init_chat_model("gemini-2.0-flash", model_provider="google_genai")

# -------------------------
# LangGraph State
# -------------------------
class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]

graph_builder = StateGraph(State)

def chatbot(state: State):
    response_message = llm.invoke(state["messages"])
    return {"messages": [response_message]}

graph_builder.add_node("chatbot", chatbot)
graph_builder.add_edge(START, "chatbot")
graph_builder.add_edge("chatbot", END)
graph = graph_builder.compile()

# -------------------------
# Flask App
# -------------------------
app = Flask(__name__)
user_sessions = {}

# Scheduler for reminders and daily tips
scheduler = BackgroundScheduler()
scheduler.start()

# Clean expired users daily
scheduler.add_job(clean_expired_users, 'interval', days=1)

# Schedule daily mental health tips (7:00 AM every day)
scheduler.add_job(
    lambda: send_daily_mental_health_tips(),
    'cron', 
    hour=7, 
    minute=0,
    id='daily_mental_health_tips',
    name='Send Daily Mental Health Tips'
)

print("✅ Scheduler started")
print("✅ Daily mental health tips scheduled for 7:00 AM")

# Schedule weekly progress reports (Every Sunday at 8:00 PM)
scheduler.add_job(
    lambda: send_weekly_progress_reports(),
    'cron',
    day_of_week='sun',  # Sunday
    hour=20,            # 8 PM
    minute=0,
    id='weekly_progress_reports',
    name='Weekly Progress Reports'
)

print("✅ Weekly progress reports scheduled (Sundays at 8 PM)")

# -------------------------
# System Prompt (Updated for conversational responses)
# -------------------------
fitness_system_prompt = SystemMessage(
    content=(
        "You are NexiFit, a helpful and conversational fitness assistant. "
        "You help users with workouts, nutrition, diet plans, and fitness advice.\n\n"
        "**Response Guidelines:**\n"
        "1. When providing an INITIAL workout plan, use this structured format:\n\n"
        "   *Today's Workout Plan:* (or specify Daily/Weekly if requested)\n"
        "   - Exercise 1: details\n"
        "   - Exercise 2: details\n"
        "   Estimated Time: ~X minutes\n\n"
        "   *Nutrition Plan:* (Macros & Nutritional Guidelines)\n"
        "   - Daily protein target: Xg\n"
        "   - Daily calorie target: X calories\n"
        "   - Carbs/Fats ratio: ...\n"
        "   - Hydration: X liters water\n\n"
        "   *Diet Plan:* (Actual Meal Suggestions)\n"
        "   - Breakfast: ...\n"
        "   - Lunch: ...\n"
        "   - Dinner: ...\n"
        "   - Snacks: ...\n\n"
        "   *Recovery:*\n"
        "   - Sleep: X hours\n"
        "   - Rest days: ...\n"
        "   - Stretching: ...\n\n"
        "2. IMPORTANT: Always specify workout duration:\n"
        "   - If no time restriction mentioned: Provide 'Today's Workout Plan'\n"
        "   - If user wants routine: Provide 'Weekly Workout Plan' (Mon-Sun)\n"
        "   - Always be clear about the timeframe\n\n"
        "3. NUTRITION vs DIET:\n"
        "   - Nutrition Plan = Numbers (calories, protein, carbs, fats, hydration)\n"
        "   - Diet Plan = Actual food/meals (breakfast, lunch, dinner)\n\n"
        "4. For FOLLOW-UP questions or conversations:\n"
        "   - Be natural and conversational\n"
        "   - Answer questions directly and clearly\n"
        "   - Keep responses concise (2-4 paragraphs max)\n"
        "   - Use bullet points only when listing multiple items\n"
        "   - Be encouraging and supportive\n\n"
        "5. Always stay on fitness topics: workouts, diet, nutrition, exercise, health, recovery, etc.\n"
        "6. If asked about workout modifications, alternatives, or specific exercises, answer directly.\n"
        "7. Keep tone friendly, motivating, and professional.\n"
        "8. Avoid emojis unless the user uses them first."
    )
)

# -------------------------
# MENTAL HEALTH TIPS FUNCTIONS
# -------------------------

def send_daily_mental_health_tips():
    """
    Send mental health tips to all eligible users every morning at 7 AM.
    Called by APScheduler automatically.
    """
    print(f"\n{'='*50}")
    print(f"🌅 Starting daily mental health tips broadcast - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}")
    
    # Get all users who should receive tips
    users = get_users_for_daily_tips()
    
    if not users:
        print("⚠️ No users found to send tips to")
        return
    
    success_count = 0
    error_count = 0
    
    for user in users:
        try:
            phone_number = user['phone_number']
            name = user['name'] or "there"
            
            # Get next tip for this user
            tip = get_next_tip_for_user(phone_number)
            
            if not tip:
                print(f"⚠️ No tips available for {phone_number}")
                error_count += 1
                continue
            
            # Format the message
            category_emoji = {
                'motivation': '💪',
                'stress': '🧘',
                'mindfulness': '🧠',
                'sleep': '😴',
                'positivity': '✨',
                'general': '💭'
            }
            
            emoji = category_emoji.get(tip['category'], '💭')
            
            message = (
                f"🌅 Good morning, {name}!\n\n"
                f"{emoji} *Today's Mental Wellness Tip:*\n\n"
                f"{tip['tip_text']}\n\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"Remember: A healthy mind supports a healthy body! 💪🧠\n\n"
                f"_Reply 'STOP TIPS' to unsubscribe from daily tips._"
            )
            
            # Send via Twilio
            client.messages.create(
                from_=TWILIO_WHATSAPP_NUMBER,
                to=phone_number,
                body=message
            )
            
            # Log the tip
            log_tip_sent(phone_number, tip['id'])
            
            print(f"✅ Sent tip to {phone_number} (Category: {tip['category']})")
            success_count += 1
            
        except Exception as e:
            print(f"❌ Error sending tip to {phone_number}: {e}")
            error_count += 1
    
    print(f"\n{'='*50}")
    print(f"📊 Daily Tips Summary:")
    print(f"   ✅ Successful: {success_count}")
    print(f"   ❌ Failed: {error_count}")
    print(f"   📱 Total Users: {len(users)}")
    print(f"{'='*50}\n")

def send_weekly_progress_reports():
    """Send weekly progress reports to all users every Sunday."""
    print(f"\n{'='*50}")
    print(f"📊 Sending Weekly Progress Reports - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}")
    
    users = get_users_for_weekly_report()
    success_count = 0
    
    for user in users:
        try:
            phone_number = user['phone_number']
            name = user['name'] or "Champion"
            
            # Get user's weekly progress
            progress = get_weekly_progress(phone_number)
            
            if not progress:
                # User hasn't worked out this week
                message = (
                    f"📊 *Weekly Progress Report*\n\n"
                    f"Hey {name}! 👋\n\n"
                    f"We noticed you haven't logged any workouts this week.\n\n"
                    f"💪 Even a 15-minute workout counts!\n"
                    f"Let's get back on track. Ready? 🚀"
                )
            else:
                # User has workout data
                workouts = progress['workouts_completed']
                minutes = int(progress['total_minutes'])
                calories = int(progress['total_calories'])
                progress_pct = round(progress['avg_progress'], 1)
                goal = progress['goal']
                
                # Format time
                hours = minutes // 60
                remaining_mins = minutes % 60
                time_str = f"{hours}h {remaining_mins}m" if hours > 0 else f"{remaining_mins} min"
                
                # Choose emoji based on performance
                if workouts >= 5:
                    emoji = "🔥"
                    praise = "Outstanding"
                elif workouts >= 3:
                    emoji = "💪"
                    praise = "Great job"
                else:
                    emoji = "👍"
                    praise = "Good start"
                
                message = (
                    f"📊 *Your Weekly Progress Report*\n\n"
                    f"{emoji} *{praise}, {name}!*\n\n"
                    f"━━━━━━━━━━━━━━━━\n"
                    f"📅 *This Week's Stats:*\n\n"
                    f"✅ Workouts: *{workouts}*\n"
                    f"⏱️ Time: *{time_str}*\n"
                    f"🔥 Calories: *~{calories} kcal*\n"
                    f"📈 Progress: *{progress_pct}%* closer\n\n"
                    f"🎯 *Goal:* {goal}\n\n"
                    f"━━━━━━━━━━━━━━━━\n"
                    f"Keep the momentum! 🚀"
                )
            
            # Send message
            client.messages.create(
                from_=TWILIO_WHATSAPP_NUMBER,
                to=phone_number,
                body=message
            )
            
            print(f"✅ Sent report to {phone_number}")
            success_count += 1
            
        except Exception as e:
            print(f"❌ Error sending to {phone_number}: {e}")
    
    print(f"📊 Sent {success_count} reports\n{'='*50}\n")


def handle_tip_admin_commands(sender, incoming_msg):
    """
    Handle admin commands for mental health tips management.
    Returns response message or None if not a tip command.
    """
    
    if not is_admin(sender):
        return None
    
    msg = incoming_msg.strip()
    msg_upper = msg.upper()
    
    # ADD TIP: ADMIN ADD_TIP category: text
    if msg_upper.startswith("ADMIN ADD_TIP"):
        try:
            # Parse: ADMIN ADD_TIP motivation: Your tip text here
            content = msg[14:].strip()  # Remove "ADMIN ADD_TIP "
            
            if ':' in content:
                category, tip_text = content.split(':', 1)
                category = category.strip().lower()
                tip_text = tip_text.strip()
            else:
                category = 'general'
                tip_text = content
            
            if len(tip_text) < 10:
                return "⚠️ Tip text too short. Minimum 10 characters."
            
            success, message, tip_id = add_mental_health_tip(tip_text, category)
            
            if success:
                return f"✅ Tip added successfully!\nID: {tip_id}\nCategory: {category}\nPreview: {tip_text[:100]}..."
            else:
                return f"⚠️ {message}"
                
        except Exception as e:
            return f"⚠️ Error: {str(e)}\n\nUsage:\nADMIN ADD_TIP category: tip text\nExample:\nADMIN ADD_TIP motivation: You are stronger than you think!"
    
    # LIST TIPS: ADMIN LIST_TIPS [category]
    elif msg_upper.startswith("ADMIN LIST_TIPS"):
        parts = incoming_msg.split()
        category_filter = parts[2].lower() if len(parts) > 2 else None
        
        tips = get_all_mental_health_tips(active_only=True)
        
        if category_filter:
            tips = [tip for tip in tips if tip['category'] == category_filter]
        
        if not tips:
            return f"📋 No tips found{' for category: ' + category_filter if category_filter else ''}"
        
        # Group by category
        categories = {}
        for tip in tips:
            cat = tip['category']
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(tip)
        
        response = f"📋 *Mental Health Tips* ({len(tips)} total)\n\n"
        
        for cat, cat_tips in sorted(categories.items()):
            response += f"━━ {cat.upper()} ({len(cat_tips)}) ━━\n"
            for tip in cat_tips[:3]:  # Show first 3 per category
                preview = tip['tip_text'][:80] + "..." if len(tip['tip_text']) > 80 else tip['tip_text']
                response += f"  #{tip['id']}: {preview}\n"
            if len(cat_tips) > 3:
                response += f"  ... and {len(cat_tips) - 3} more\n"
            response += "\n"
        
        response += "\n💡 Use: ADMIN VIEW_TIP <id> to see full tip"
        return response
    
    # VIEW SPECIFIC TIP: ADMIN VIEW_TIP <id>
    elif msg_upper.startswith("ADMIN VIEW_TIP"):
        parts = msg.split()
        if len(parts) < 3:
            return "⚠️ Usage: ADMIN VIEW_TIP <tip_id>"
        
        try:
            tip_id = int(parts[2])
            tip = get_tip_by_id(tip_id)
            
            if not tip:
                return f"⚠️ Tip #{tip_id} not found"
            
            status = "✅ Active" if tip['active'] else "❌ Inactive"
            
            return (
                f"📋 *Tip #{tip['id']}*\n\n"
                f"Category: {tip['category']}\n"
                f"Status: {status}\n"
                f"Added: {tip['date_added'][:10]}\n\n"
                f"Text:\n{tip['tip_text']}"
            )
        except ValueError:
            return "⚠️ Invalid tip ID. Must be a number."
    
    # DEACTIVATE TIP: ADMIN REMOVE_TIP <id>
    elif msg_upper.startswith("ADMIN REMOVE_TIP"):
        parts = msg.split()
        if len(parts) < 3:
            return "⚠️ Usage: ADMIN REMOVE_TIP <tip_id>"
        
        try:
            tip_id = int(parts[2])
            success, message = deactivate_tip(tip_id)
            return f"{'✅' if success else '⚠️'} {message}"
        except ValueError:
            return "⚠️ Invalid tip ID. Must be a number."
    
    # ACTIVATE TIP: ADMIN ACTIVATE_TIP <id>
    elif msg_upper.startswith("ADMIN ACTIVATE_TIP"):
        parts = msg.split()
        if len(parts) < 3:
            return "⚠️ Usage: ADMIN ACTIVATE_TIP <tip_id>"
        
        try:
            tip_id = int(parts[2])
            success, message = activate_tip(tip_id)
            return f"{'✅' if success else '⚠️'} {message}"
        except ValueError:
            return "⚠️ Invalid tip ID. Must be a number."
    
    # TIP STATISTICS: ADMIN TIP_STATS [phone_number]
    elif msg_upper.startswith("ADMIN TIP_STATS"):
        parts = msg.split()
        
        if len(parts) > 2:
            # Stats for specific user
            phone_number = parts[2]
            stats = get_user_tip_stats(phone_number)
            
            return (
                f"📊 *Tip Stats for {phone_number}*\n\n"
                f"Total Tips Received: {stats['total_tips_received']}\n"
                f"Last 30 Days: {stats['tips_last_30_days']}\n"
                f"Last Tip Date: {stats['last_tip_date'] or 'Never'}"
            )
        else:
            # Global stats
            stats = get_global_tip_stats()
            
            response = "📊 *Global Tip Statistics*\n\n"
            response += f"Active Tips: {stats['total_active_tips']}\n"
            response += f"Tips Sent Today: {stats['tips_sent_today']}\n"
            response += f"Users Enabled: {stats['users_with_tips_enabled']}\n\n"
            response += "Tips by Category:\n"
            
            for cat, count in stats['tips_by_category'].items():
                response += f"  • {cat}: {count}\n"
            
            return response
    
    # TEST TIP: ADMIN TEST_TIP <phone_number>
    elif msg_upper.startswith("ADMIN TEST_TIP"):
        parts = msg.split()
        if len(parts) < 3:
            return "⚠️ Usage: ADMIN TEST_TIP <phone_number>"
        
        phone_number = parts[2]
        
        try:
            # Get next tip
            tip = get_next_tip_for_user(phone_number)
            
            if not tip:
                return "⚠️ No tips available"
            
            # Send test message
            category_emoji = {
                'motivation': '💪',
                'stress': '🧘',
                'mindfulness': '🧠',
                'sleep': '😴',
                'positivity': '✨',
                'general': '💭'
            }
            
            emoji = category_emoji.get(tip['category'], '💭')
            
            message = (
                f"🧪 *TEST TIP*\n\n"
                f"{emoji} *Mental Wellness Tip:*\n\n"
                f"{tip['tip_text']}\n\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"Category: {tip['category']}\n"
                f"Tip ID: #{tip['id']}"
            )
            
            client.messages.create(
                from_=TWILIO_WHATSAPP_NUMBER,
                to=phone_number,
                body=message
            )
            
            return f"✅ Test tip sent to {phone_number}\nCategory: {tip['category']}\nTip ID: #{tip['id']}"
            
        except Exception as e:
            return f"⚠️ Error sending test tip: {str(e)}"
    
    # BROADCAST TIP NOW: ADMIN BROADCAST_TIP
    elif msg_upper.startswith("ADMIN BROADCAST_TIP"):
        try:
            send_daily_mental_health_tips()
            return "✅ Broadcasting tips to all users... Check console for details."
        except Exception as e:
            return f"⚠️ Error broadcasting tips: {str(e)}"
    
    # TIP HELP
    elif msg_upper == "ADMIN TIP_HELP":
        return (
            "💭 *Mental Health Tips Commands:*\n\n"
            "ADMIN ADD_TIP category: text\n"
            "ADMIN LIST_TIPS [category]\n"
            "ADMIN VIEW_TIP <id>\n"
            "ADMIN REMOVE_TIP <id>\n"
            "ADMIN ACTIVATE_TIP <id>\n"
            "ADMIN TIP_STATS [phone]\n"
            "ADMIN TEST_TIP <phone>\n"
            "ADMIN BROADCAST_TIP\n\n"
            "Categories: motivation, stress, mindfulness, sleep, positivity, general"
        )
    
    return None


# -------------------------
# ADMIN COMMAND HANDLERS
# -------------------------

def handle_admin_command(sender, incoming_msg):
    """Handle admin commands for user management."""
    
    if not is_admin(sender):
        return None
    
    # CHECK FOR TIP COMMANDS FIRST
    tip_response = handle_tip_admin_commands(sender, incoming_msg)
    if tip_response:
        return tip_response
    
    msg = incoming_msg.upper().strip()
    
    # ADD USER: ADMIN ADD whatsapp:+1234567890 [Name] [Days]
    if msg.startswith("ADMIN ADD"):
        parts = incoming_msg.split()
        if len(parts) < 3:
            return "⚠️ Usage: ADMIN ADD <phone_number> [name] [expiry_days]\nExample: ADMIN ADD whatsapp:+1234567890 John 30"
        
        phone = parts[2]
        name = parts[3] if len(parts) > 3 else None
        days = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else None
        
        success, message = add_user(phone, name, days)
        return f"{'✅' if success else '⚠️'} {message}"
    
    # REMOVE USER: ADMIN REMOVE whatsapp:+1234567890
    elif msg.startswith("ADMIN REMOVE"):
        parts = incoming_msg.split()
        if len(parts) < 3:
            return "⚠️ Usage: ADMIN REMOVE <phone_number>"
        
        phone = parts[2]
        success, message = remove_user(phone)
        return f"{'✅' if success else '⚠️'} {message}"
    
    # REACTIVATE USER: ADMIN REACTIVATE whatsapp:+1234567890
    elif msg.startswith("ADMIN REACTIVATE"):
        parts = incoming_msg.split()
        if len(parts) < 3:
            return "⚠️ Usage: ADMIN REACTIVATE <phone_number>"
        
        phone = parts[2]
        success, message = reactivate_user(phone)
        return f"{'✅' if success else '⚠️'} {message}"
    
    # LIST USERS: ADMIN LIST
    elif msg.startswith("ADMIN LIST"):
        users = list_all_users()
        if not users:
            return "📋 No users in database"
        
        response = "📋 *Authorized Users:*\n\n"
        for user in users[:20]:
            status = "✅" if user['authorized'] else "❌"
            expiry = f" (Expires: {user['expiry_date'][:10]})" if user['expiry_date'] else ""
            response += f"{status} {user['phone_number']}{expiry}\n"
        
        if len(users) > 20:
            response += f"\n... and {len(users) - 20} more users"
        
        return response
    
    # USER INFO: ADMIN INFO whatsapp:+1234567890
    elif msg.startswith("ADMIN INFO"):
        parts = incoming_msg.split()
        if len(parts) < 3:
            return "⚠️ Usage: ADMIN INFO <phone_number>"
        
        phone = parts[2]
        user = get_user_info(phone)
        
        if not user:
            return "⚠️ User not found"
        
        status = "Active ✅" if user['authorized'] else "Inactive ❌"
        expiry = user['expiry_date'] if user['expiry_date'] else "No expiry"
        
        return (f"📋 *User Info:*\n"
                f"Phone: {user['phone_number']}\n"
                f"Name: {user['name'] or 'N/A'}\n"
                f"Status: {status}\n"
                f"Added: {user['date_added'][:10]}\n"
                f"Expiry: {expiry}")
    
    # TEST WEEKLY REPORT
    elif msg.startswith("ADMIN TEST_REPORT"):
        parts = msg.split()
        if len(parts) < 3:
            return "⚠️ Usage: ADMIN TEST_REPORT <phone_number>"
        
        phone = parts[2]
        progress = get_weekly_progress(phone)
        
        if not progress:
            return f"📊 No workout data for {phone} in last 7 days"
        
        return (
            f"📊 *Weekly Stats for {phone}*\n\n"
            f"Workouts: {progress['workouts_completed']}\n"
            f"Minutes: {int(progress['total_minutes'])}\n"
            f"Calories: {int(progress['total_calories'])}\n"
            f"Progress: {round(progress['avg_progress'], 1)}%\n"
            f"Goal: {progress['goal']}"
        )
    
    # SEND REPORTS NOW
    elif msg == "ADMIN SEND_REPORTS":
        send_weekly_progress_reports()
        return "✅ Sending weekly reports now... Check console!"

    # ADMIN HELP
    elif msg.startswith("ADMIN HELP") or msg == "ADMIN":
        return (
            "🔐 *Admin Commands:*\n\n"
            "📱 USER MANAGEMENT:\n"
            "ADMIN ADD <phone> [name] [days]\n"
            "ADMIN REMOVE <phone>\n"
            "ADMIN REACTIVATE <phone>\n"
            "ADMIN LIST\n"
            "ADMIN INFO <phone>\n\n"
            "💭 MENTAL HEALTH TIPS:\n"
            "ADMIN TIP_HELP\n\n"
            "Example:\n"
            "ADMIN ADD whatsapp:+1234567890 John 30"
        )
    
    return None

# -------------------------
# Reminder Helper Functions
# -------------------------
def send_reminder(task, sender):
    """Send reminder via Twilio."""
    client.messages.create(
        from_=TWILIO_WHATSAPP_NUMBER,
        to=sender,
        body=f"⏰ Reminder: {task}"
    )
    print(f"Sent reminder to {sender}: {task}")

def parse_reminder_message(message):
    """Parse reminder messages with regex."""
    message = message.lower().strip()

    # Relative time: "in X minutes/hours"
    match_relative = re.search(r"remind me to (.+) in (\d+)\s*(second|seconds|minute|minutes|hour|hours)", message)
    if match_relative:
        task = match_relative.group(1).strip()
        amount = int(match_relative.group(2))
        unit = match_relative.group(3)

        if "hour" in unit:
            remind_time = datetime.now() + timedelta(hours=amount)
        elif "minute" in unit:
            remind_time = datetime.now() + timedelta(minutes=amount)
        else:
            remind_time = datetime.now() + timedelta(seconds=amount)
        return task, remind_time

    # Absolute time: "at HH:MM"
    match_absolute = re.search(r"remind me to (.+) at (\d{1,2}):(\d{2})", message)
    if match_absolute:
        task = match_absolute.group(1).strip()
        hour = int(match_absolute.group(2))
        minute = int(match_absolute.group(3))
        now = datetime.now()
        remind_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if remind_time < now:
            remind_time += timedelta(days=1)
        return task, remind_time

    return None, None

def schedule_reminder(sender, task, run_time):
    """Schedule a reminder job."""
    scheduler.add_job(send_reminder, "date", run_date=run_time, args=[task, sender])
    print(f"Reminder set for {sender} at {run_time}")

# -------------------------
# Helper: Check if message is fitness-related
# -------------------------
def is_fitness_related(message):
    """Check if message is fitness-related with broader keyword matching."""
    message_lower = message.lower()
    
    # Expanded fitness keywords
    fitness_keywords = [
        "workout", "diet", "gym", "exercise", "yoga", "health", "fitness",
        "calories", "nutrition", "training", "protein", "cardio", "strength",
        "weight", "muscle", "fat", "run", "walk", "jog", "swim", "cycle",
        "stretch", "warm", "cool", "rest", "recovery", "sleep", "meal",
        "food", "eat", "drink", "water", "supplement", "vitamin", "carb",
        "plan", "routine", "schedule", "goal", "body", "abs", "leg", "arm",
        "chest", "back", "shoulder", "core", "squat", "push", "pull", "lift",
        "rep", "set", "intensity", "duration", "time", "minute", "hour",
        "injury", "pain", "sore", "tired", "energy", "motivation", "progress"
    ]
    
    # Question words - allow fitness-related questions
    question_words = ["what", "how", "why", "when", "where", "can", "should", 
                      "could", "would", "is", "are", "do", "does", "tell", "show"]
    
    # Check if it's a fitness keyword OR a question (likely fitness-related in context)
    has_fitness_keyword = any(word in message_lower for word in fitness_keywords)
    is_question = any(message_lower.startswith(word) or f" {word} " in message_lower 
                     for word in question_words)
    
    # Also allow short messages (likely follow-ups) after onboarding is done
    is_short_followup = len(message.split()) <= 5
    
    return has_fitness_keyword or (is_question and is_short_followup)

# -------------------------
# Background reply processor (UPDATED)
# -------------------------
def process_and_reply(sender, is_initial_plan=False):
    try:
        session = user_sessions[sender]

        # Prepare system + context
        system_context = SystemMessage(
            content=(
                f"User's details:\n"
                f"- Name: {session['name']}\n"
                f"- Age: {session['age']}\n"
                f"- Gender: {session['gender']}\n"
                f"- Weight: {session['weight']}\n"
                f"- Height: {session['height']}\n"
                f"- Goal: {session['fitness_goal']}\n"
                f"- Injuries: {session['injury']}\n"
                f"- Today's Restrictions: {session.get('user_restrictions', 'None')}\n\n"
                f"Request type: {'INITIAL PLAN - Provide a complete plan for TODAY' if is_initial_plan else 'FOLLOW-UP QUESTION - Answer conversationally'}.\n\n"
                "Instructions:\n"
                + ("- Create a complete workout, nutrition, and diet plan for TODAY\n"
                   "- Clearly label it as 'Today's Workout Plan' at the top\n"
                   "- Include estimated total workout time in minutes\n"
                   "- Nutrition Plan should have macro targets (protein, calories, carbs, fats, water)\n"
                   "- Diet Plan should have actual meal suggestions (breakfast, lunch, dinner, snacks)\n"
                   "- Adjust based on user's time restrictions and injuries" if is_initial_plan else 
                   "- Answer the user's question directly and conversationally\n"
                   "- Reference their goals and restrictions when relevant\n"
                   "- Keep response concise and helpful")
            )
        )

        state = {"messages": [fitness_system_prompt, system_context] + session["messages"]}
        result = graph.invoke(state)
        response_text = result["messages"][-1].content

        # Only add reminder prompt and schedule motivational message for initial plans
        if is_initial_plan:
            # Extract Estimated Workout Time
            match_time = re.search(r"Estimated Time:\s*~?(\d+)\s*minutes?", response_text, re.IGNORECASE)
            workout_minutes = int(match_time.group(1)) if match_time else None
            calories_burned = None
            progress_percent = None

            # Estimate Calories Burned & Progress
            if workout_minutes and session.get("weight") and session.get("fitness_goal"):
                try:
                    weight = float(re.findall(r"\d+", str(session["weight"]))[0])
                    goal = str(session["fitness_goal"]).lower()

                    if "muscle" in goal:
                        MET = 8
                    elif "weight" in goal or "fat" in goal:
                        MET = 6
                    elif "cardio" in goal:
                        MET = 7
                    else:
                        MET = 5

                    calories_burned = int(workout_minutes * MET * 3.5 * weight / 200)
                    progress_percent = min(round(workout_minutes / 10, 1), 100)

                    # 🆕 Save workout to database
                    log_workout_completion(
                        sender, 
                        workout_minutes, 
                        calories_burned, 
                        progress_percent, 
                        session["fitness_goal"]
                    )

                except Exception as e:
                    print("Calorie calculation error:", e)

            # Add Reminder Help Prompt
            if "would you like to set any reminders" not in response_text.lower():
                response_text += (
                    "\n\nWould you like to set any reminders for your workouts or meals?\n\n"
                    "You can say:\n"
                    "- Remind me to <task> in <minutes>\n"
                    "- Remind me to <task> at <HH:MM>"
                )

            # Schedule Motivational Message After Workout
            if workout_minutes:
                motivational_msg = (
                    f"🔥 Great job, {session['name']}!\n\n"
                    f"Today you lost approximately {calories_burned or 0} calories "
                    f"and you're about {progress_percent or 0}% closer to your goal: *{session['fitness_goal']}*.\n"
                    "Keep it up! 💪"
                )
                run_time = datetime.now() + timedelta(minutes=workout_minutes)
                scheduler.add_job(
                    client.messages.create,
                    "date",
                    run_date=run_time,
                    kwargs={
                        "from_": TWILIO_WHATSAPP_NUMBER,
                        "to": sender,
                        "body": motivational_msg
                    }
                )
                print(f"Motivational message scheduled for {sender} in {workout_minutes} min")

        # Send Main LLM Response
        chunks = [response_text[i:i + 1500] for i in range(0, len(response_text), 1500)]
        session["messages"].append(result["messages"][-1])

        total_parts = len(chunks)
        for idx, chunk in enumerate(chunks, start=1):
            if total_parts > 1:
                body = f"(Part {idx}/{total_parts})\n\n{chunk}"
            else:
                body = chunk

            client.messages.create(
                from_=TWILIO_WHATSAPP_NUMBER,
                to=sender,
                body=body
            )
            print(f"DEBUG reply part {idx}/{total_parts}: {len(chunk)} chars")

    except Exception as e:
        print("Error in process_and_reply:", e)
        # Send error message to user
        try:
            client.messages.create(
                from_=TWILIO_WHATSAPP_NUMBER,
                to=sender,
                body="⚠️ Sorry, I encountered an error. Please try asking your question again."
            )
        except:
            pass

# -------------------------
# Webhook for WhatsApp
# -------------------------
@app.route("/whatsapp", methods=["POST"])
def whatsapp_webhook():
    incoming_msg = request.form.get("Body", "").strip()
    sender = request.form.get("From")
    print(f"📩 Incoming from {sender}: {incoming_msg}")

    # =============================
    # 🔐 AUTHENTICATION CHECK
    # =============================
    
    # Check if admin command
    if incoming_msg.upper().startswith("ADMIN"):
        admin_response = handle_admin_command(sender, incoming_msg)
        if admin_response:
            resp = MessagingResponse()
            resp.message(admin_response)
            log_auth_attempt(sender, "admin_command", success=True)
            return str(resp)
    
    # Check if user is authorized
    if not is_user_authorized(sender):
        log_auth_attempt(sender, "unauthorized_access", success=False)
        resp = MessagingResponse()
        resp.message(
            f"⛔ *Access Denied*\n\n"
            f"Your number is not authorized to use NexiFit.\n\n"
            f"Please contact the admin to get access:\n"
            f"📧 {ADMIN_CONTACT}"
        )
        print(f"❌ Unauthorized access attempt: {sender}")
        return str(resp)
    
    # Log successful authentication
    log_auth_attempt(sender, "authorized_access", success=True)
    
    # =============================
    # ONBOARDING & CONVERSATION
    # =============================

    if sender not in user_sessions:
        user_sessions[sender] = {
            "messages": [],
            "onboarding_step": "basic",
            "name": None,
            "age": None,
            "gender": None,
            "weight": None,
            "height": None,
            "fitness_goal": None,
            "injury": None,
            "reminders": [],
            "last_goal_check": datetime.now(),
            "user_restrictions": None
        }

        # Greeting message
        combined_intro = (
            "💪 Hey there! I'm *NexiFit*, your personal fitness companion.\n\n"
            "I'll help you design smart workouts, balanced meals, and keep you on track — all right here on WhatsApp!\n\n"
            "Before we begin, could you please tell me your details in this format?\n\n"
            "👉 *Name , Age , Gender*\n\n"
            "Example: Kishore , 25 , Male"
        )

        resp = MessagingResponse()
        resp.message(combined_intro)

        # threading.Timer(2.0, lambda: client.messages.create(
        #     from_=TWILIO_WHATSAPP_NUMBER,
        #     to=sender,
        #     body=combined_intro
        # )).start()

        print(f"✅ New authorized user greeted: {sender}")
        return str(resp)

    session = user_sessions[sender]

    # Step 1: Basic Info
    if session["onboarding_step"] == "basic":
        try:
            parts = [p.strip() for p in incoming_msg.split(",")]
            session["name"] = parts[0] if len(parts) > 0 else None
            session["age"] = parts[1] if len(parts) > 1 else None
            session["gender"] = parts[2] if len(parts) > 2 else None

            resp = MessagingResponse()
            resp.message(
                f"✅ Got it!\n- Name: {session['name']}\n- Age: {session['age']}\n- Gender: {session['gender']}\n\n"
                "Do you have any *time & injury restrictions* today?\n\n"
                "Example: 'Yes, only 30 minutes' , 'Mild knee pain' , 'No restrictions'"
            )
            session["onboarding_step"] = "restrictions"
            return str(resp)

        except Exception:
            resp = MessagingResponse()
            resp.message("⚠️ Please reply in format: Name , Age , Gender")
            return str(resp)

    # Step 1.5: Restrictions
    if session["onboarding_step"] == "restrictions":
        session["user_restrictions"] = incoming_msg.strip()
        session["onboarding_step"] = "personalize"

        resp = MessagingResponse()
        resp.message(
            f"✅ Thanks! I'll consider your restriction: '{session['user_restrictions']}'.\n\n"
            "Do you want to make it more personalised?\n\n"
            "👉 If yes, reply: Weight , Height , Goal , Injuries (if any)\n"
            "👉 If no, just type 'No'"
        )
        return str(resp)

    # Step 2: Personalization
    if session["onboarding_step"] == "personalize":
        if incoming_msg.lower() == "no":
            session["onboarding_step"] = "done"
            session["messages"].append(HumanMessage(content="Suggest a personalized starting plan for me."))
            threading.Thread(target=process_and_reply, args=(sender, True)).start()
            resp = MessagingResponse()
            resp.message("🎯 Okay, preparing a general plan for you...")
            return str(resp)

        try:
            parts = [p.strip() for p in incoming_msg.split(",")]
            session["weight"] = parts[0] if len(parts) > 0 else None
            session["height"] = parts[1] if len(parts) > 1 else None
            session["fitness_goal"] = parts[2] if len(parts) > 2 else None
            session["injury"] = parts[3] if len(parts) > 3 else "None"
            session["onboarding_step"] = "done"

            resp = MessagingResponse()
            resp.message(
                f"✅ Thanks {session['name']}! Got your details:\n"
                f"- Age: {session['age']}\n- Gender: {session['gender']}\n"
                f"- Weight: {session['weight']}\n- Height: {session['height']}\n"
                f"- Goal: {session['fitness_goal']}\n- Injury: {session['injury']}\n\n"
                "🎯 Let me suggest a personalised plan for your goal..."
            )

            session["messages"].append(HumanMessage(content="Suggest a personalized starting plan for me."))
            threading.Thread(target=process_and_reply, args=(sender, True)).start()
            
            # # Send helpful tips after a delay
            # def send_tips():
            #     tips_msg = (
            #         "\n💡 *Quick Tips:*\n\n"
            #         "You can ask me:\n"
            #         "• 'Give me a weekly plan'\n"
            #         "• 'What's my plan for today?'\n"
            #         "• 'Can I substitute X with Y?'\n"
            #         "• 'How many calories in chicken?'\n"
            #         "• 'Set reminder for workout in 30 minutes'\n\n"
            #         "I'm here to help! 💪"
            #     )
            #     client.messages.create(
            #         from_=TWILIO_WHATSAPP_NUMBER,
            #         to=sender,
            #         body=tips_msg
            #     )
            
            # threading.Timer(5.0, send_tips).start()
            
            return str(resp)
        except Exception:
            resp = MessagingResponse()
            resp.message("⚠️ Please reply in format: Weight , Height , Goal , Injuries")
            return str(resp)

    # Step 3: Normal conversation
    if session["onboarding_step"] == "done":
        
        # ===== HANDLE TIP OPT-OUT/OPT-IN =====
        msg_lower = incoming_msg.lower().strip()
        
        if msg_lower in ['stop tips', 'no tips', 'disable tips', 'unsubscribe tips']:
            set_user_tip_preference(sender, False)
            resp = MessagingResponse()
            resp.message(
                "✅ You've been unsubscribed from daily mental health tips.\n\n"
                "You can re-enable them anytime by sending 'START TIPS'."
            )
            return str(resp)
        
        if msg_lower in ['start tips', 'enable tips', 'resume tips', 'subscribe tips']:
            set_user_tip_preference(sender, True)
            resp = MessagingResponse()
            resp.message(
                "✅ Daily mental health tips enabled!\n\n"
                "You'll receive a morning wellness tip every day at 7:00 AM. 🌅"
            )
            return str(resp)
        # ===== END TIP HANDLING =====
        
        # Handle reminders
        if "remind" in incoming_msg.lower():
            try:
                task, run_time = parse_reminder_message(incoming_msg)
                if task and run_time:
                    session["reminders"].append({"text": task, "time": run_time})
                    schedule_reminder(sender, task, run_time)
                    resp = MessagingResponse()
                    resp.message(f"✅ Reminder set: '{task}' at {run_time.strftime('%H:%M:%S')}")
                    return str(resp)
                else:
                    raise ValueError("Invalid reminder format")
            except Exception as e:
                print("Reminder error:", e)
                resp = MessagingResponse()
                resp.message("⚠️ Couldn't set reminder. Use:\n- Remind me to <task> in <minutes>\n- Remind me to <task> at <HH:MM>")
                return str(resp)

        # Handle weekly/daily plan requests
        msg_lower = incoming_msg.lower()
        if any(word in msg_lower for word in ["weekly plan", "week plan", "7 day", "full week", "weekly routine", "weekly workout"]):
            session["messages"].append(HumanMessage(
                content=f"Create a complete weekly workout plan (Monday to Sunday) for me based on my goal: {session['fitness_goal']}. "
                        f"Include rest days and specify which muscle groups to target each day."
            ))
            resp = MessagingResponse()
            resp.message("📅 Creating your weekly workout plan...")
            threading.Thread(target=process_and_reply, args=(sender, True)).start()
            return str(resp)
        
        elif any(word in msg_lower for word in ["today", "today's plan", "workout for today"]):
            session["messages"].append(HumanMessage(
                content="What's my workout plan for today?"
            ))
            resp = MessagingResponse()
            resp.message("📋 Preparing today's workout plan...")
            threading.Thread(target=process_and_reply, args=(sender, True)).start()
            return str(resp)

        # IMPROVED: More lenient fitness topic check
        if not is_fitness_related(incoming_msg):
            resp = MessagingResponse()
            resp.message(
                "⚠️ I specialize in fitness topics like workouts, diet, nutrition, and exercise.\n\n"
                "Feel free to ask me anything about your fitness journey! 💪"
            )
            return str(resp)

        # Add message to history and process
        session["messages"].append(HumanMessage(content=incoming_msg))
        print(f"💬 Processing message. History length: {len(session['messages'])}")

        resp = MessagingResponse()
        resp.message("✅ Got it! Let me help you with that...")
        threading.Thread(target=process_and_reply, args=(sender, False)).start()
        return str(resp)

# -------------------------
# Weekly Goal Check Feature
# -------------------------
def weekly_goal_check():
    while True:
        now = datetime.now()
        for phone, data in user_sessions.items():
            try:
                last_check = data.get("last_goal_check")
                if last_check and (now - last_check).days >= 7:
                    client.messages.create(
                        from_=TWILIO_WHATSAPP_NUMBER,
                        to=phone,
                        body="It's been a week! Would you like to update your fitness goal or weight?"
                    )
                    data["last_goal_check"] = now
            except Exception as e:
                print("Weekly goal check error:", e)
        threading.Event().wait(86400)

threading.Thread(target=weekly_goal_check, daemon=True).start()


# -------------------------
# Auto-initialize database on startup
# -------------------------
def initialize_database():
    """Initialize database tables if they don't exist."""
    import sqlite3
    
    conn = sqlite3.connect('nexifit_users.db')
    cursor = conn.cursor()
    
    # Create authorized users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS authorized_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone_number TEXT UNIQUE NOT NULL,
            name TEXT,
            authorized INTEGER DEFAULT 1,
            date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expiry_date TIMESTAMP,
            notes TEXT
        )
    ''')
    
    # Create admin users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone_number TEXT UNIQUE NOT NULL,
            name TEXT,
            date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create audit log table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS auth_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone_number TEXT NOT NULL,
            action TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            success INTEGER DEFAULT 0
        )
    ''')
    
    conn.commit()
    
    # Add default admin (⚠️ CHANGE THIS TO YOUR WHATSAPP NUMBER!)
    default_admin = "whatsapp:+918667643749"  # ⚠️ CHANGE THIS!
    
    try:
        cursor.execute('''
            INSERT INTO admin_users (phone_number, name) 
            VALUES (?, ?)
        ''', (default_admin, "System Admin"))
        
        cursor.execute('''
            INSERT INTO authorized_users (phone_number, name, authorized) 
            VALUES (?, ?, 1)
        ''', (default_admin, "System Admin"))
        
        conn.commit()
        print(f"✅ Default admin initialized: {default_admin}")
    except sqlite3.IntegrityError:
        print("ℹ️ Admin already exists")
    
    conn.close()
    print("✅ Database initialized successfully!")

# Initialize database on startup
initialize_database()


@app.route("/health")
def health():
    return "OK", 200

if __name__ == "__main__":
    app.run(port=5000, debug=True)
