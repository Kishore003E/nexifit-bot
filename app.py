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
    get_user_info, clean_expired_users
)

# -------------------------
# Twilio credentials
# -------------------------
TWILIO_SID = os.environ.get("TWILIO_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.environ.get("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")
ADMIN_CONTACT = os.environ.get("ADMIN_CONTACT", "admin@nexifit.com")  # For user contact

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

# Scheduler for reminders
scheduler = BackgroundScheduler()
scheduler.start()

# Clean expired users daily
scheduler.add_job(clean_expired_users, 'interval', days=1)

# -------------------------
# System Prompt (fitness-only)
# -------------------------
fitness_system_prompt = SystemMessage(
    content=(
        "You are a helpful fitness assistant named NexiFit. "
        "Always respond briefly, clearly, and in a structured way with bold section titles and spacing for readability.\n\n"
        "Output format must be:\n"
        "Workout Plan:\n"
        "- ...\n"
        "Estimated Time: ~X minutes\n\n"
        "Diet Plan:\n"
        "- ...\n\n"
        "Nutrition Plan:\n"
        "- ...\n\n"
        "Recovery:\n"
        "- ...\n\n"
        "Rules:\n"
        "- Keep each section short and clear.\n"
        "- Always include 'Estimated Time' after the Workout Plan.\n"
        "- Use bold formatting (**) only for section titles.\n"
        "- Leave one blank line between sections.\n"
        "- Avoid long explanations, emojis, or decorative symbols."
    )
)

# -------------------------
# ADMIN COMMAND HANDLERS
# -------------------------

def handle_admin_command(sender, incoming_msg):
    """Handle admin commands for user management."""
    
    if not is_admin(sender):
        return None  # Not an admin command or not authorized
    
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
        for user in users[:20]:  # Limit to 20 to avoid long messages
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
    
    # ADMIN HELP
    elif msg.startswith("ADMIN HELP") or msg == "ADMIN":
        return (
            "🔐 *Admin Commands:*\n\n"
            "ADMIN ADD <phone> [name] [days]\n"
            "ADMIN REMOVE <phone>\n"
            "ADMIN REACTIVATE <phone>\n"
            "ADMIN LIST\n"
            "ADMIN INFO <phone>\n\n"
            "Example:\n"
            "ADMIN ADD whatsapp:+1234567890 John 30"
        )
    
    return None  # Not an admin command

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
        else:  # seconds
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
# Background reply processor
# -------------------------
def process_and_reply(sender):
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
                "Please personalize advice accordingly. Adjust workout intensity and duration based on today's restrictions.\n"
                "Always include an estimated total workout time in minutes for the 'Workout Plan' section."
            )
        )

        state = {"messages": [fitness_system_prompt, system_context] + session["messages"]}
        result = graph.invoke(state)
        response_text = result["messages"][-1].content

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
    
    # Check if admin command (admins can always use commands)
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
        greeting = (
            "💪 Hey there! I'm *NexiFit*, your personal fitness companion.\n\n"
            "I'll help you design smart workouts, balanced meals, and keep you on track — all right here on WhatsApp!"
        )

        intro = (
            "Before we begin, could you please tell me your details in this format?\n\n"
            "👉 *Name , Age , Gender*\n\n"
            "Example: Kishore , 25 , Male"
        )

        resp = MessagingResponse()
        resp.message(greeting)

        threading.Timer(2.0, lambda: client.messages.create(
            from_=TWILIO_WHATSAPP_NUMBER,
            to=sender,
            body=intro
        )).start()

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
                "Do you have any **time or injury restrictions** today?\n\n"
                "Example: 'Yes, only 30 minutes' or 'Mild knee pain' or 'No restrictions'"
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
            threading.Thread(target=process_and_reply, args=(sender,)).start()
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
            threading.Thread(target=process_and_reply, args=(sender,)).start()
            return str(resp)
        except Exception:
            resp = MessagingResponse()
            resp.message("⚠️ Please reply in format: Weight , Height , Goal , Injuries")
            return str(resp)

    # Step 3: Normal conversation
    if session["onboarding_step"] == "done":
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

        # Guard: only fitness topics
        fitness_keywords = ["workout", "diet", "gym", "exercise", "yoga", "health",
                            "fitness", "calories", "nutrition", "training", "protein"]
        if not any(word in incoming_msg.lower() for word in fitness_keywords):
            resp = MessagingResponse()
            resp.message("⚠️ I can only talk about fitness topics or reminders. Please try again!")
            return str(resp)

        session["messages"].append(HumanMessage(content=incoming_msg))
        print("history:", session["messages"])

        resp = MessagingResponse()
        resp.message("✅ Got your message, working on it…")
        threading.Thread(target=process_and_reply, args=(sender,)).start()
        return str(resp)

# -------------------------
# Weekly Goal Check Feature
# -------------------------
def weekly_goal_check():
    while True:
        now = datetime.now()
        for phone, data in user_sessions.items():
            try:
                # Check if one week has passed since last goal check
                last_check = data.get("last_goal_check")
                if last_check and (now - last_check).days >= 7:
                    client.messages.create(
                        from_=TWILIO_WHATSAPP_NUMBER,
                        to=phone,
                        body="It's been a week! Would you like to update your fitness goal or weight?"
                    )
                    data["last_goal_check"] = now  # reset the timer
            except Exception as e:
                print("Weekly goal check error:", e)
        # Check daily
        threading.Event().wait(86400)

# Start the weekly goal check thread
threading.Thread(target=weekly_goal_check, daemon=True).start()


@app.route("/health")
def health():
    return "OK", 200

# -------------------------
# Main
# -------------------------
if __name__ == "__main__":
    app.run(port=5000, debug=True)