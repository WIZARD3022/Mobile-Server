from flask import Flask, request, jsonify
import json, os
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

app = Flask(__name__)
load_dotenv()

DATA_FILE = os.getenv("Datafile")
PORT = int(os.getenv("PORT"))

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
        }
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=True)
