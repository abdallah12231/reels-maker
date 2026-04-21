import os
import json
import re
import subprocess
import uuid
from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
import anthropic

app = Flask(__name__)
CORS(app)

# إعداد المجلدات
DOWNLOAD_DIR = "downloads"
OUTPUT_DIR = "outputs"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# إعداد عميل الذكاء الاصطناعي
client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

# --- الصفحة الرئيسية (الواجهة) ---
@app.route("/")
def home():
    try:
        # هيفتح ملف index.html اللي أنت رفعته في فولدر templates
        return render_template("index.html")
    except Exception as e:
        return f"Error: index.html not found in templates folder. {str(e)}"

# --- وظائف الفيديو ---
def download_video(url: str, job_id: str) -> str:
    output_path = os.path.join(DOWNLOAD_DIR, f"{job_id}.mp4")
    cmd = [
        "yt-dlp",
        "--no-check-certificates",
        "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
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
      "description": "وصف جذاب للريلز مناسب لليوتيوب شورتس",
      "hashtags": "#هاشتاج1 #هاشتاج2"
    }}
  ]
}}
"""
    message = client.messages.create(
        model="claude-3-sonnet-20240229", # تم تحديث اسم الموديل ليكون صحيحاً
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )
    
    text = message.content[0].text.strip()
    text = re.sub(r"```json|```", "", text).strip()
    data = json.loads(text)
    return data["reels"]

# --- الروابط (EndPoints) ---
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
        video_path = download_video(url, job_id)
        duration = get_video_duration(video_path)
        reels = analyze_video_with_ai(url, duration)

        results = []
        for i, reel in enumerate(reels):
            output_filename = f"{job_id}_reel_{i+1}.mp4"
            output_path = os.path.join(OUTPUT_DIR, output_filename)
            start = min(reel["start"], duration - 10)
            end = min(reel["end"], duration)
            cut_video(video_path, start, end, output_path)

            results.append({
                "reel_number": i + 1,
                "title": reel["title"],
                "description": reel["description"],
                "hashtags": reel["hashtags"],
                "download_url": f"/download/{output_filename}"
            })

        os.remove(video_path)
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
    # استخدام بورت 8080 كما هو مضبوط في Railway
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
