import os
import json
import re
import subprocess
import uuid
import requests
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import anthropic

app = Flask(__name__)
CORS(app)

DOWNLOAD_DIR = "downloads"
OUTPUT_DIR = "outputs"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))


def download_video(url: str, job_id: str) -> str:
    output_path = os.path.join(DOWNLOAD_DIR, f"{job_id}.mp4")
    cmd = [
        "yt-dlp",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", output_path,
        url
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"Download failed: {result.stderr}")
    return output_path


def get_video_duration(video_path: str) -> float:
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", video_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def cut_video(video_path: str, start: float, end: float, output_path: str):
    duration = end - start
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-i", video_path,
        "-t", str(duration),
        "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
        "-c:v", "libx264", "-c:a", "aac",
        "-preset", "fast",
        output_path
    ]
    subprocess.run(cmd, capture_output=True)


def analyze_video_with_ai(url: str, duration: float) -> list:
    prompt = f"""
أنت خبير في تحليل محتوى الفيديو وإنشاء ريلز جذابة.

لدي فيديو من هذا الرابط: {url}
مدة الفيديو: {duration:.0f} ثانية

مهمتك: اختر من 3 إلى 5 أجزاء من الفيديو تكون الأكثر إثارة وجذباً للمشاهد لتحويلها إلى ريلز.

كل ريلز يجب أن:
- تكون مدتها بين 30 و90 ثانية
- تبدأ وتنتهي في نقطة منطقية
- تحتوي على محتوى مثير ومشوّق

أجب فقط بـ JSON بهذا الشكل بدون أي نص إضافي:
{{
  "reels": [
    {{
      "start": 0,
      "end": 60,
      "title": "عنوان الريلز",
      "description": "وصف جذاب للريلز مناسب لليوتيوب شورتس (3-4 جمل)",
      "hashtags": "#هاشتاج1 #هاشتاج2 #هاشتاج3 #هاشتاج4 #هاشتاج5"
    }}
  ]
}}
"""
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )
    
    text = message.content[0].text.strip()
    text = re.sub(r"```json|```", "", text).strip()
    data = json.loads(text)
    return data["reels"]


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/process", methods=["POST"])
def process_video():
    data = request.json
    url = data.get("url")
    if not url:
        return jsonify({"error": "URL مطلوب"}), 400

    job_id = str(uuid.uuid4())[:8]

    try:
        # 1. Download video
        print(f"Downloading video: {url}")
        video_path = download_video(url, job_id)

        # 2. Get duration
        duration = get_video_duration(video_path)
        print(f"Video duration: {duration}s")

        # 3. Analyze with AI
        print("Analyzing with AI...")
        reels = analyze_video_with_ai(url, duration)

        # 4. Cut reels
        results = []
        for i, reel in enumerate(reels):
            output_filename = f"{job_id}_reel_{i+1}.mp4"
            output_path = os.path.join(OUTPUT_DIR, output_filename)

            start = min(reel["start"], duration - 10)
            end = min(reel["end"], duration)

            print(f"Cutting reel {i+1}: {start}s - {end}s")
            cut_video(video_path, start, end, output_path)

            results.append({
                "reel_number": i + 1,
                "title": reel["title"],
                "description": reel["description"],
                "hashtags": reel["hashtags"],
                "start": start,
                "end": end,
                "download_url": f"/download/{output_filename}"
            })

        # Cleanup original
        os.remove(video_path)

        # 5. Send to Zapier if webhook URL is set
        zapier_webhook = os.environ.get("ZAPIER_WEBHOOK_URL")
        if zapier_webhook:
            for reel in results:
                server_url = os.environ.get("SERVER_URL", "")
                zapier_data = {
                    "title": reel["title"],
                    "description": f"{reel['description']}\n\n{reel['hashtags']}",
                    "video_url": f"{server_url}{reel['download_url']}",
                    "reel_number": reel["reel_number"]
                }
                try:
                    requests.post(zapier_webhook, json=zapier_data, timeout=10)
                    print(f"Sent reel {reel['reel_number']} to Zapier")
                except Exception as ze:
                    print(f"Zapier error: {ze}")

        return jsonify({"success": True, "reels": results})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/download/<filename>", methods=["GET"])
def download_file(filename):
    file_path = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404
    return send_file(file_path, as_attachment=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
import os
import json
import re
import subprocess
import uuid
import requests
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import anthropic

app = Flask(__name__)
CORS(app)

DOWNLOAD_DIR = "downloads"
OUTPUT_DIR = "outputs"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))


def download_video(url: str, job_id: str) -> str:
    output_path = os.path.join(DOWNLOAD_DIR, f"{job_id}.mp4")
    cmd = [
        "yt-dlp",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", output_path,
        url
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"Download failed: {result.stderr}")
    return output_path


def get_video_duration(video_path: str) -> float:
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", video_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def cut_video(video_path: str, start: float, end: float, output_path: str):
    duration = end - start
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-i", video_path,
        "-t", str(duration),
        "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
        "-c:v", "libx264", "-c:a", "aac",
        "-preset", "fast",
        output_path
    ]
    subprocess.run(cmd, capture_output=True)


def analyze_video_with_ai(url: str, duration: float) -> list:
    prompt = f"""
أنت خبير في تحليل محتوى الفيديو وإنشاء ريلز جذابة.

لدي فيديو من هذا الرابط: {url}
مدة الفيديو: {duration:.0f} ثانية

مهمتك: اختر من 3 إلى 5 أجزاء من الفيديو تكون الأكثر إثارة وجذباً للمشاهد لتحويلها إلى ريلز.

كل ريلز يجب أن:
- تكون مدتها بين 30 و90 ثانية
- تبدأ وتنتهي في نقطة منطقية
- تحتوي على محتوى مثير ومشوّق

أجب فقط بـ JSON بهذا الشكل بدون أي نص إضافي:
{{
  "reels": [
    {{
      "start": 0,
      "end": 60,
      "title": "عنوان الريلز",
      "description": "وصف جذاب للريلز مناسب لليوتيوب شورتس (3-4 جمل)",
      "hashtags": "#هاشتاج1 #هاشتاج2 #هاشتاج3 #هاشتاج4 #هاشتاج5"
    }}
  ]
}}
"""
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )
    
    text = message.content[0].text.strip()
    text = re.sub(r"```json|```", "", text).strip()
    data = json.loads(text)
    return data["reels"]


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/process", methods=["POST"])
def process_video():
    data = request.json
    url = data.get("url")
    if not url:
        return jsonify({"error": "URL مطلوب"}), 400

    job_id = str(uuid.uuid4())[:8]

    try:
        # 1. Download video
        print(f"Downloading video: {url}")
        video_path = download_video(url, job_id)

        # 2. Get duration
        duration = get_video_duration(video_path)
        print(f"Video duration: {duration}s")

        # 3. Analyze with AI
        print("Analyzing with AI...")
        reels = analyze_video_with_ai(url, duration)

        # 4. Cut reels
        results = []
        for i, reel in enumerate(reels):
            output_filename = f"{job_id}_reel_{i+1}.mp4"
            output_path = os.path.join(OUTPUT_DIR, output_filename)

            start = min(reel["start"], duration - 10)
            end = min(reel["end"], duration)

            print(f"Cutting reel {i+1}: {start}s - {end}s")
            cut_video(video_path, start, end, output_path)

            results.append({
                "reel_number": i + 1,
                "title": reel["title"],
                "description": reel["description"],
                "hashtags": reel["hashtags"],
                "start": start,
                "end": end,
                "download_url": f"/download/{output_filename}"
            })

        # Cleanup original
        os.remove(video_path)

        # 5. Send to Zapier if webhook URL is set
        zapier_webhook = os.environ.get("ZAPIER_WEBHOOK_URL")
        if zapier_webhook:
            for reel in results:
                server_url = os.environ.get("SERVER_URL", "")
                zapier_data = {
                    "title": reel["title"],
                    "description": f"{reel['description']}\n\n{reel['hashtags']}",
                    "video_url": f"{server_url}{reel['download_url']}",
                    "reel_number": reel["reel_number"]
                }
                try:
                    requests.post(zapier_webhook, json=zapier_data, timeout=10)
                    print(f"Sent reel {reel['reel_number']} to Zapier")
                except Exception as ze:
                    print(f"Zapier error: {ze}")

        return jsonify({"success": True, "reels": results})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/download/<filename>", methods=["GET"])
def download_file(filename):
    file_path = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404
    return send_file(file_path, as_attachment=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
