from flask import Flask, request, jsonify
import json, os, random
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)
load_dotenv()


DATA_FILE = os.getenv("Datafile")
PORT = int(os.getenv("PORT"))
UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER")
QUOTES_FILE = os.getenv("QUOTES_FILE")

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

# ---------------- SCHEDULER ----------------

scheduler = BackgroundScheduler()

def start_scheduler():
    scheduler.add_job(
        set_quote,
        trigger="cron",
        hour=18,
        minute=30
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
    print(data)
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
    print(request.json)
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
    print(data)
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
    if "audio" not in request.files:
        return jsonify({"error": "No audio file"}), 400

    audio = request.files["audio"]
    filepath = os.path.join(UPLOAD_FOLDER, audio.filename)
    audio.save(filepath)

    return jsonify({"status": "success", "file": filepath})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=True)
