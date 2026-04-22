from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from dotenv import load_dotenv
import os
import json
from fastapi import WebSocket
import asyncio

# Load environment variables
load_dotenv()

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = FastAPI()

# Enable CORS (for frontend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

log_history = []

def detect_patterns(logs):
    error_count = sum(1 for log in logs if "ERROR" in log)
    warning_count = sum(1 for log in logs if "WARNING" in log)

    prediction = "Stable"

    if error_count > 3:
        prediction = "High chance of failure"
    elif warning_count > 5:
        prediction = "Potential instability"

    return {
        "error_count": error_count,
        "warning_count": warning_count,
        "prediction": prediction
    }

@app.get("/")
def home():
    return {"message": "AI Observability Copilot Backend Running 🚀"}


@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    content = await file.read()
    logs = content.decode("utf-8")

    prompt = f"""
You are an expert SRE (Site Reliability Engineer).

Analyze the following logs and return STRICT JSON ONLY in this format:

{{
  "errors": ["list of errors"],
  "root_cause": "short explanation",
  "severity": "Low | Medium | High",
  "suggestions": ["list of actionable fixes"]
}}

Logs:
{logs}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}],
        )

        content = response.choices[0].message.content.strip()

        # Try parsing JSON safely
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            parsed = {
                "errors": [],
                "root_cause": "Could not parse AI response",
                "severity": "Medium",
                "suggestions": [content]
            }

        return parsed

    except Exception as e:
        return {
            "errors": ["Internal server error"],
            "root_cause": str(e),
            "severity": "High",
            "suggestions": ["Check backend logs"]
        }

@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    await websocket.accept()

    try:
        while True:
            data = await websocket.receive_text()

            # Store logs
            log_history.append(data)

            # Keep last 20 logs only
            if len(log_history) > 20:
                log_history.pop(0)

            pattern_result = detect_patterns(log_history)

            prompt = f"""
You are an SRE expert.

Analyze logs and return JSON:

{{
  "errors": ["..."],
  "root_cause": "...",
  "severity": "Low | Medium | High",
  "suggestions": ["..."]
}}

Logs:
{data}
"""

            response = client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[{"role": "user", "content": prompt}],
            )

            ai_content = response.choices[0].message.content

            try:
                ai_json = json.loads(ai_content)
            except:
                ai_json = {
                    "errors": [],
                    "root_cause": "Parsing error",
                    "severity": "Medium",
                    "suggestions": []
                }

            # Merge AI + pattern detection
            final_output = {
                **ai_json,
                "metrics": pattern_result
            }

            await websocket.send_text(json.dumps(final_output))

    except Exception:
        await websocket.close()