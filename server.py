from flask import Flask, request, jsonify
import json, os, random
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from datetime import datetime, date
from apscheduler.schedulers.background import BackgroundScheduler
from google import genai
from google.genai import types

app = Flask(__name__)
load_dotenv()


DATA_FILE = os.getenv("Datafile")
PORT = int(os.getenv("PORT"))
UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER")
QUOTES_FILE = os.getenv("QUOTES_FILE")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TASK_FILE = os.getenv("TASK_FILE")
MAX_TASKS_PER_WEEK = os.getenv("TASKS_PER_WEEK")
DAILY_TASK_FILE = os.getenv("DAILY_TASK_FILE")

client = genai.Client(api_key=GEMINI_API_KEY)

# ---------------- QUOTE LOGIC ----------------

def get_random_quote():
    with open(QUOTES_FILE, "r", encoding="utf-8") as file:
        quotes = [line.strip().strip(",").strip('"') for line in file if line.strip()]
    return random.choice(quotes)

quote = get_random_quote()

def set_quote():
    global quote
    quote = get_random_quote()
    print(f"🌙 Quote changed at {datetime.now()}")

def history_uptime():
    today_str = date.today().isoformat()
    if not os.path.exists(DAILY_TASK_FILE):
        return jsonify({
            "status": "error",
            "message": "Task file not found",
            "tasks": []
        }), 404

    with open(DAILY_TASK_FILE, "r", encoding="utf-8") as f:
        tasks = json.load(f)

    updated = False

    for task in tasks:
        if task.get("date") == today_str:
            if task.get("status") == "Not Now":
                task["status"] = "Incomplete"
                updated = True
            break  # today’s task found, stop loop

    # Save only if change happened
    if updated:
        with open(DAILY_TASK_FILE, "w", encoding="utf-8") as f:
            json.dump(tasks, f, indent=2, ensure_ascii=False)

    print(f"🌙 Times up for daily chalange on {datetime.now()}")

# ---------------- SCHEDULER ----------------

scheduler = BackgroundScheduler()

def scheduled_tasks():
    set_quote()
    history_uptime()

def start_scheduler():
    scheduler.add_job(
        scheduled_tasks,
        trigger="cron",
        hour=18,
        minute=38
    )
    scheduler.start()

# Prevent double scheduler in debug mode
if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
    start_scheduler()

def load_users():
    if not os.path.exists(DATA_FILE):
        return {"users": []}
    with open(DATA_FILE, "r") as f:
        return json.load(f)


def save_users(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

def generate_weekly_tasks():
    # -------------------------
    # Load user data
    # -------------------------
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    user = data["users"][0]

    # -------------------------
    # Analyze capacity
    # -------------------------
    history = user.get("Data", [])
    history_count = len(history) if history else 0
    avg_daily_capacity = max(3, min(6, history_count + 2))
    max_weekly = MAX_TASKS_PER_WEEK if isinstance(MAX_TASKS_PER_WEEK, int) else 30
    weekly_capacity = min(max_weekly, avg_daily_capacity * 7)


    # -------------------------
    # Extract base tasks
    # -------------------------
    base_tasks = []
    for task in user.get("tasks", []):
        base_tasks.append({
            "title": task["title"],
            "area": task["area"],
            "description": task["description"],
            "fields": [f["field_name"] for f in task["required_fields"]]
        })

    # -------------------------
    # Build prompt
    # -------------------------
    prompt = f"""
You are a smart task planning AI.

User:
- Username: {user['username']}
- Join date: {user['profile']['join_date']}
- Weekly capacity: {weekly_capacity}

Existing task patterns:
{json.dumps(base_tasks, indent=2)}

Rules:
- Generate exactly {weekly_capacity} tasks
- Tasks must be derived from existing areas
- Difficulty must match capacity
- Each task must include:
  - Title
  - Area
  - Short description
  - Estimated time (minutes)

Return ONLY a numbered list.
"""

    # -------------------------
    # Gemini call (NEW API)
    # -------------------------
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )

    tasks_text = response.text.strip()

    # -------------------------
    # Save file
    # -------------------------
    with open(TASK_FILE, "w", encoding="utf-8") as f:
        f.write("WEEKLY AI TASK PLAN\n")
        f.write(f"Generated on: {datetime.now()}\n\n")
        f.write(tasks_text)

    return weekly_capacity, tasks_text

def parse_tasks(task_file):
    tasks = []
    current_task = []

    with open(task_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if not line:
                continue

            # Detect start of new task (e.g. "1.  Title:")
            if line[0].isdigit() and "Title:" in line:
                if current_task:
                    tasks.append("\n".join(current_task))
                    current_task = []

            # Only start collecting after Title appears
            if "Title:" in line or current_task:
                current_task.append(line)

        if current_task:
            tasks.append("\n".join(current_task))

    return tasks

def get_today_task():
    today_str = date.today().isoformat()
    history = []

    # 1️⃣ Load existing data safely
    if os.path.exists(DAILY_TASK_FILE):
        with open(DAILY_TASK_FILE, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)

                # 🔥 OLD FORMAT → convert to list
                if isinstance(data, dict) and "date" in data and "task" in data:
                    history = [data]

                # ✅ NEW FORMAT
                elif isinstance(data, list):
                    history = data

            except json.JSONDecodeError:
                history = []

    # 2️⃣ Check if today's task already exists
    for entry in history:
        if isinstance(entry, dict) and entry.get("date") == today_str:
            return entry.get("task"), entry.get("status")

    # 3️⃣ Load tasks
    if not os.path.exists(TASK_FILE):
        return "No tasks available.", None

    tasks = parse_tasks(TASK_FILE)
    if not tasks:
        return "No tasks available.", None

    # 4️⃣ Pick random task
    task_today = random.choice(tasks)
    state = "Not Now"

    # 5️⃣ Append today's task
    history.append({
        "date": today_str,
        "task": task_today,
        "status": state
    })

    # 6️⃣ Save back (append-safe)
    with open(DAILY_TASK_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    return task_today, state


# ✅ SIGN UP
@app.route("/signup", methods=["POST"])
def signup():
    data = request.json
    username = data.get("username")
    email = data.get("email")
    password = data.get("password")

    users_data = load_users()

    for user in users_data["users"]:
        if user["email"] == email:
            return jsonify({"status": "error", "message": "User already exists"}), 400

    new_user = {
        "username": username,
        "email": email,
        "password": generate_password_hash(password),
        "profile": {
            "tasks_completed": 0,
            "join_date": "2025-12-23"
        },
        "tasks": [],   # ✅ ADD THIS
        "Data": []
    }


    users_data["users"].append(new_user)
    save_users(users_data)

    return jsonify({"status": "success"})


# ✅ SIGN IN
@app.route("/signin", methods=["POST"])
def signin():
    data = request.json
    email = data.get("email")
    password = data.get("password")

    users_data = load_users()

    for user in users_data["users"]:
        if user["email"] == email:
            if check_password_hash(user["password"], password):
                return jsonify({
                    "status": "success",
                    "username": user["username"],
                    "profile": user["profile"]
                })
            else:
                return jsonify({"status": "error", "message": "Wrong password"}), 401

    return jsonify({"status": "error", "message": "User not found"}), 404

@app.route("/add_task", methods=["POST"])
def add_task():
    data = request.json
    email = data.get("email")
    task = data.get("task")

    users_data = load_users()

    for user in users_data["users"]:
        if user["email"] == email:
            user["tasks"].append(task)
            save_users(users_data)
            return jsonify({"status": "success", "tasks": user["tasks"]})

    return jsonify({"status": "error", "message": "User not found"}), 404


@app.route("/get_tasks", methods=["POST"])
def get_tasks():
    data = request.json
    email = data.get("email")

    users_data = load_users()

    for user in users_data["users"]:
        if user["email"] == email:
            return jsonify({"status": "success", "tasks": user.get("tasks", [])})

    return jsonify({"status": "error"}), 404


@app.route("/delete_task", methods=["POST"])
def delete_task():
    data = request.json
    email = data.get("email")
    index = data.get("index")

    users_data = load_users()

    for user in users_data["users"]:
        if user["email"] == email:
            user["tasks"].pop(index)
            save_users(users_data)
            return jsonify({"status": "success", "tasks": user["tasks"]})

    return jsonify({"status": "error"}), 404


@app.route("/getProfile", methods=["POST"])
def get_profile():
    email = request.json.get("email")

    users_data = load_users()

    for user in users_data["users"]:
        if user["email"] == email:
            print("found task", user.get("tasks", []))
            return jsonify({"status": "success", "tasks": user.get("tasks", [])})
    return jsonify({"status": "error"}), 404

@app.route("/updateProfile", methods=["POST"])
def update_profile():
    data = request.json
    email = data.get("email")
    tasks = data.get("tasks")  # expecting list of tasks

    users_data = load_users()

    for user in users_data["users"]:
        if user["email"] == email:

            values_only = []

            for task in tasks:
                for field in task.get("required_fields", []):
                    value = field.get("value")
                    if value is not None:
                        values_only.append(value)

            # Create timestamp
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            entry = {
                "timestamp": timestamp,
                "values": values_only
            }

            # Ensure Data exists
            if "Data" not in user:
                user["Data"] = []

            user["Data"].append(entry)
            save_users(users_data)

            return jsonify({
                "status": "success",
                "message": "Profile updated",
                "timestamp": timestamp
            })

    return jsonify({
        "status": "error",
        "message": "User not found"
    }), 404

@app.route("/getquote", methods=["POST"])
def get_quote():
    return jsonify({"status": "success", "quote": quote})


@app.route("/trackData", methods=["POST"])
def track_data():
    data = request.json
    email = data.get("email")

    users_data = load_users()

    for user in users_data["users"]:
        if user["email"] == email:
            print({"status": "success", "tasks": user.get("tasks", []), "Data": user.get("Data", [])})
            return jsonify({"status": "success", "tasks": user.get("tasks", []), "Data": user.get("Data", [])})

    return jsonify({
        "status": "error",
        "message": "User not found"
    }), 404

@app.route("/upload_audio", methods=["POST"])
def upload_audio():
    email = request.form.get("email")
    if not email:
        return jsonify({"error": "Email is required"}), 400

    if "audio" not in request.files:
        return jsonify({"error": "No audio file"}), 400

    audio = request.files["audio"]

    # Ensure base upload folder exists
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    # Create email-specific folder
    user_folder = os.path.join(UPLOAD_FOLDER, email)
    os.makedirs(user_folder, exist_ok=True)

    # Generate date & timestamp filename
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    file_ext = os.path.splitext(audio.filename)[1]  # keep original extension
    new_filename = f"audio_{timestamp}{file_ext}"

    filepath = os.path.join(user_folder, new_filename)
    audio.save(filepath)

    return jsonify({
        "status": "success",
        "file": filepath,
        "email": email
    })

@app.route("/generate-weekly-tasks", methods=["POST"])
def generate_tasks_api():
    count, text = generate_weekly_tasks()
    return jsonify({
        "status": "success",
        "tasks_generated": count,
        "saved_to": TASK_FILE,
        "preview": text[:500]
    })

@app.route("/today-task", methods=["GET", "POST"])
def today_task_api():
    task, state = get_today_task()
    return jsonify({
        "status": "success",
        "date": date.today().isoformat(),
        "task": task,
        "state": state
    })

@app.route("/complete-today-task", methods=["GET", "POST"])
def complete_today_task_api():
    today_str = date.today().isoformat()

    if not os.path.exists(DAILY_TASK_FILE):
        return False  # file not found

    with open(DAILY_TASK_FILE, "r", encoding="utf-8") as f:
        try:
            history = json.load(f)
        except json.JSONDecodeError:
            return False

    if not isinstance(history, list):
        return False

    updated = False

    for entry in history:
        if entry.get("date") == today_str:
            entry["status"] = "Complete"
            updated = True
            break

    if updated:
        with open(DAILY_TASK_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)

    return jsonify({
        "status": "success"
    })

@app.route("/all-tasks", methods=["GET"])
def get_all_tasks():
    if not os.path.exists(DAILY_TASK_FILE):
        return jsonify({
            "status": "error",
            "message": "Task file not found",
            "tasks": []
        }), 404

    with open(DAILY_TASK_FILE, "r", encoding="utf-8") as f:
        tasks = json.load(f)

    return jsonify({
        "status": "success",
        "total": len(tasks),
        "tasks": tasks
    }), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=True)
