from flask import Flask, render_template, send_from_directory, redirect, url_for
import os
import wave
import whisper

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ===== AUDIO CONFIG =====
SAMPLE_RATE = 44100
CHANNELS = 1
SAMPLE_WIDTH = 2

# ===== WHISPER =====
model = whisper.load_model("base")


def process_user_audio(user_folder):
    """Process ALL audio for a user"""
    user_path = os.path.join(UPLOAD_FOLDER, user_folder)

    for filename in os.listdir(user_path):
        file_path = os.path.join(user_path, filename)

        # PCM → WAV
        if filename.endswith(".pcm"):
            wav_path = file_path.replace(".pcm", ".wav")

            if not os.path.exists(wav_path):
                with open(file_path, "rb") as pcm:
                    data = pcm.read()

                with wave.open(wav_path, "wb") as wav:
                    wav.setnchannels(CHANNELS)
                    wav.setsampwidth(SAMPLE_WIDTH)
                    wav.setframerate(SAMPLE_RATE)
                    wav.writeframes(data)

            os.remove(file_path)  # 🧹 delete PCM

        # Speech-to-text
    for filename in os.listdir(user_path):
        if filename.endswith(".wav"):
            wav_path = os.path.join(user_path, filename)
            txt_path = wav_path.replace(".wav", ".txt")

            if os.path.exists(txt_path):
                continue

            result = model.transcribe(wav_path)
            text = result["text"]
            language = result.get("language", "unknown")

            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(f"Language: {language}\n\n{text}")


@app.route("/")
def users():
    users = [
        d for d in os.listdir(UPLOAD_FOLDER)
        if os.path.isdir(os.path.join(UPLOAD_FOLDER, d))
    ]
    return render_template("users.html", users=users)


@app.route("/user/<username>")
def user_page(username):
    user_path = os.path.join(UPLOAD_FOLDER, username)
    if not os.path.isdir(user_path):
        return "User not found", 404

    # 🔁 AUTO PROCESS EVERYTHING
    process_user_audio(username)

    audios = []
    for f in os.listdir(user_path):
        if f.endswith(".wav"):
            name = f.replace(".wav", "")
            txt = f.replace(".wav", ".txt")

            txt_content = ""
            txt_path = os.path.join(user_path, txt)
            if os.path.exists(txt_path):
                with open(txt_path, "r", encoding="utf-8") as t:
                    txt_content = t.read()

            audios.append({
                "file": f,
                "text": txt_content
            })

    return render_template(
        "user_audio.html",
        username=username,
        audios=audios
    )


@app.route("/media/<username>/<filename>")
def media(username, filename):
    return send_from_directory(
        os.path.join(UPLOAD_FOLDER, username),
        filename
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=1234, debug=True)
