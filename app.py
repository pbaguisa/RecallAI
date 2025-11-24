"""
RecallAI - RAG-Powered Study Assistant
Main Flask Application
"""

from flask import Flask, request, jsonify, render_template_string
import os
import time
import json
from datetime import datetime
from dotenv import load_dotenv
import google.generativeai as genai

# Import our custom modules
from rag import RAGSystem
from utils import validate_input, check_safety, extract_pdf_text

import google.generativeai as genai
import os

# Configure the Gemini API key
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))

# # List available models
# try:
#     models = genai.list_models()  # This fetches the available models
#     print("Available Models:")
#     for model in models:
#         print(model)  # Print each available model
# except Exception as e:
#     print(f"Error fetching models: {e}")


# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB max file size
app.config["UPLOAD_FOLDER"] = "uploads"

# Create upload folder if it doesn't exist
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# Initialize Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash")

# Initialize RAG system
rag = RAGSystem()

# System prompt
SYSTEM_PROMPT = """You are RecallAI, a study assistant that helps students learn from lecture slides.

DO:
- Answer questions based ONLY on the provided lecture slide content
- Generate quiz questions that test specific concepts from the slides
- Provide clear explanations when students forfeit quiz questions
- Cite which lecture/slide section information comes from
- Admit when information is not in the provided slides

DON'T:
- Make up information not present in the lecture slides
- Help with academic dishonesty or cheating
- Answer questions unrelated to the study material
- Provide quiz answers without the student attempting first
- Include personal opinions or external information not from slides

When summarizing: Create clear topic headings and concise bullet points.
When quizzing: Ask specific, answerable questions from the slide content."""


def log_request(query, mode, pathway, start_time, tokens, cost, metadata=None):
    """Log request telemetry to telemetry.jsonl (best-effort, non-fatal if it fails)."""
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "mode": mode,
        "pathway": pathway,
        "query": (query or "")[:100],
        "latency_ms": int((time.time() - start_time) * 1000),
        "tokens": tokens,
        "cost_usd": cost,
        "metadata": metadata or {},
    }
    try:
        with open("telemetry.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception:
        # Don't crash the app just because logging failed
        pass


def call_llm(prompt, context=""):
    """Call Gemini LLM with optional context."""
    full_prompt = f"{SYSTEM_PROMPT}\n\n"

    if context:
        full_prompt += f"Lecture Content:\n{context}\n\n"

    full_prompt += f"User Query: {prompt}"

    response = model.generate_content(full_prompt)

    # Super rough token estimate
    tokens = len(full_prompt.split()) + len((response.text or "").split())
    cost = 0.0  # assume free tier

    return response.text, tokens, cost


@app.route("/")
def home():
    """Serve the main HTML interface."""
    return render_template_string(HTML_TEMPLATE)


@app.route("/upload", methods=["POST"])
def upload_pdf():
    """Handle PDF upload."""
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files are supported"}), 400

    try:
        # Save file
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
        file.save(filepath)

        # Extract text
        text = extract_pdf_text(filepath)

        if not text or not text.strip():
            return (
                jsonify(
                    {
                        "error": "Could not extract text from PDF. "
                        "Make sure it has selectable text (not only images)."
                    }
                ),
                400,
            )

        # Add to RAG system
        rag.add_document(text, file.filename)

        return jsonify(
            {
                "success": True,
                "message": f"Successfully uploaded {file.filename}",
                "filename": file.filename,
            }
        )

    except Exception as e:
        # Show the error in the browser so you can debug
        return jsonify({"error": f"Error processing PDF: {str(e)}"}), 500


@app.route("/query", methods=["POST"])
def query():
    """Handle user queries (summary or quiz mode)."""
    start_time = time.time()

    data = request.get_json(force=True, silent=True) or {}
    user_query = data.get("query", "")
    mode = data.get("mode", "summary")  # "summary" or "quiz"

    # Validate input
    validation = validate_input(user_query)
    if validation["error"]:
        return jsonify({"error": validation["message"]}), 400

    # Safety check
    safety = check_safety(user_query)
    if not safety["safe"]:
        log_request(user_query, mode, "RAG", start_time, 0, 0, {"status": "blocked"})
        return jsonify({"error": safety["message"]}), 400

    try:
        # Check if documents are loaded in RAG system
        if not rag.has_documents():
            return jsonify({"error": "Please upload lecture PDFs before asking questions."}), 400

        # Retrieve relevant context from RAG system
        context_chunks = rag.retrieve(user_query, n_results=3)
        print(f"Context Chunks Retrieved: {context_chunks}")  # Add this to see what chunks are retrieved

        if not context_chunks:
            return jsonify({"error": "Couldn't find relevant information in your slides. Try rephrasing your question."}), 404

        context = "\n\n".join(context_chunks)

        # Modify prompt based on mode
        if mode == "quiz":
            prompt = (
                f"Generate ONE quiz question about: {user_query}\n\n"
                "The question should test understanding of the concepts in the "
                "provided lecture content. Make it specific and answerable from the slides."
            )
        else:
            prompt = user_query

        # Call LLM
        response, tokens, cost = call_llm(prompt, context)

        # Log telemetry
        log_request(
            user_query,
            mode,
            "RAG",
            start_time,
            tokens,
            cost,
            {"chunks_retrieved": len(context_chunks)},
        )

        return jsonify(
            {
                "response": response,
                "mode": mode,
                "sources": rag.get_sources(user_query),
                "latency_ms": int((time.time() - start_time) * 1000),
            }
        )

    except Exception as e:
        # Log the error for debugging
        print(f"Error during query processing: {str(e)}")  # Logs error message to the console
        log_request(
            user_query,
            mode,
            "RAG",
            start_time,
            0,
            0,
            {"error": str(e)},
        )
        return jsonify({"error": "Sorry, something went wrong. Please try again."}), 500


@app.route("/forfeit", methods=["POST"])
def forfeit():
    """Handle quiz answer forfeit."""
    start_time = time.time()

    data = request.get_json(force=True, silent=True) or {}
    question = data.get("question", "")

    try:
        # Retrieve context for the question
        context_chunks = rag.retrieve(question, n_results=2)
        context = "\n\n".join(context_chunks)

        # Get answer from LLM
        prompt = (
            f"The student asked: {question}\n\n"
            "Provide the answer with a clear explanation based on the lecture content."
        )
        response, tokens, cost = call_llm(prompt, context)

        log_request(question, "forfeit", "RAG", start_time, tokens, cost)

        return jsonify(
            {
                "answer": response,
                "latency_ms": int((time.time() - start_time) * 1000),
            }
        )

    except Exception:
        return jsonify({"error": "Could not retrieve answer."}), 500


@app.route("/status", methods=["GET"])
def status():
    """Get system status."""
    return jsonify(
        {
            "documents_loaded": rag.has_documents(),
            "total_chunks": rag.count_chunks(),
        }
    )


HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>RecallAI - Study Smarter</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 900px;
            margin: 0 auto;
        }
        .header {
            background: white;
            border-radius: 12px;
            padding: 30px;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        .header h1 {
            color: #667eea;
            font-size: 2.5em;
            margin-bottom: 10px;
        }
        .header p {
            color: #666;
            font-size: 1.1em;
        }
        .card {
            background: white;
            border-radius: 12px;
            padding: 25px;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        .upload-zone {
            border: 3px dashed #667eea;
            border-radius: 8px;
            padding: 40px;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s;
        }
        .upload-zone:hover {
            background: #f7f9ff;
            border-color: #764ba2;
        }
        .upload-zone input {
            display: none;
        }
        .btn {
            background: #667eea;
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 1em;
            transition: all 0.3s;
        }
        .btn:hover {
            background: #764ba2;
            transform: translateY(-2px);
        }
        .btn:disabled {
            background: #ccc;
            cursor: not-allowed;
            transform: none;
        }
        .mode-toggle {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
        }
        .mode-btn {
            flex: 1;
            padding: 12px;
            border: 2px solid #667eea;
            background: white;
            color: #667eea;
            border-radius: 8px;
            cursor: pointer;
            font-size: 1em;
            transition: all 0.3s;
        }
        .mode-btn.active {
            background: #667eea;
            color: white;
        }
        .query-input {
            width: 100%;
            padding: 15px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 1em;
            margin-bottom: 15px;
        }
        .query-input:focus {
            outline: none;
            border-color: #667eea;
        }
        .response-box {
            background: #f7f9ff;
            border-radius: 8px;
            padding: 20px;
            margin-top: 20px;
            min-height: 100px;
        }
        .response-box.quiz {
            background: #fff4e6;
        }
        .forfeit-btn {
            background: #ff6b6b;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 8px;
            cursor: pointer;
            margin-top: 15px;
        }
        .forfeit-btn:hover {
            background: #ee5a52;
        }
        .loading {
            text-align: center;
            color: #667eea;
            font-size: 1.1em;
            padding: 20px;
        }
        .error {
            background: #fee;
            color: #c00;
            padding: 15px;
            border-radius: 8px;
            margin-top: 15px;
        }
        .success {
            background: #efe;
            color: #060;
            padding: 15px;
            border-radius: 8px;
            margin-top: 15px;
        }
        .files-list {
            margin-top: 15px;
        }
        .file-item {
            background: #f0f0f0;
            padding: 10px;
            border-radius: 6px;
            margin-bottom: 8px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📚 RecallAI</h1>
            <p>Study smarter with AI-powered summaries and testing</p>
            <p id="statusText" style="margin-top: 8px; color: #666; font-size: 0.9em;"></p>
        </div>

        <div class="card">
            <h2>Step 1: Upload Lecture PDFs</h2>
            <div class="upload-zone" onclick="document.getElementById('fileInput').click()">
                <input type="file" id="fileInput" accept=".pdf" multiple>
                <p>📄 Click to upload PDF files</p>
                <p style="color: #999; font-size: 0.9em;">Maximum 10 PDFs, 50 pages each</p>
            </div>
            <div id="uploadStatus"></div>
            <div id="filesList" class="files-list"></div>
        </div>

        <div class="card">
            <h2>Step 2: Study Mode</h2>
            <div class="mode-toggle">
                <button class="mode-btn active" id="summaryBtn">📝 Summary Mode</button>
                <button class="mode-btn" id="quizBtn">🎯 Quiz Mode</button>
            </div>

            <input type="text" id="queryInput" class="query-input" placeholder="Ask a question or request a summary...">
            <button class="btn" id="submitBtn">Ask RecallAI</button>

            <div id="responseArea"></div>
        </div>
    </div>

    <script>
        let currentMode = 'summary';
        let uploadedFiles = [];
        let currentQuestion = '';

        // --- Status check on load ---
        async function refreshStatus() {
            try {
                const res = await fetch('/status');
                if (!res.ok) return;
                const data = await res.json();
                const el = document.getElementById('statusText');
                if (el) {
                    if (data.documents_loaded) {
                        el.textContent = `✅ Slides loaded (${data.total_chunks} chunks)`;
                    } else {
                        el.textContent = '📄 No slides uploaded yet.';
                    }
                }
            } catch (e) {
                // ignore
            }
        }

        // --- File upload handling ---
        document.getElementById('fileInput').addEventListener('change', async (e) => {
            const files = Array.from(e.target.files);
            const uploadStatus = document.getElementById('uploadStatus');
            const filesList = document.getElementById('filesList');

            for (const file of files) {
                const formData = new FormData();
                formData.append('file', file);

                uploadStatus.innerHTML = `<div class="loading">Uploading ${file.name}...</div>`;

                try {
                    const res = await fetch('/upload', {
                        method: 'POST',
                        body: formData
                    });

                    const data = await res.json();

                    if (!res.ok || data.error) {
                        uploadStatus.innerHTML = `<div class="error">❌ ${data.error || 'Upload failed'}</div>`;
                    } else {
                        uploadStatus.innerHTML = `<div class="success">✅ ${data.message}</div>`;
                        uploadedFiles.push(data.filename || file.name);
                        filesList.innerHTML = uploadedFiles
                            .map(name => `<div class="file-item">📄 ${name}</div>`)
                            .join('');
                        refreshStatus();
                    }
                } catch (err) {
                    uploadStatus.innerHTML = `<div class="error">❌ Upload failed: ${err.message}</div>`;
                }
            }
            e.target.value = '';
        });

        // --- Mode toggle ---
        document.getElementById('summaryBtn').addEventListener('click', () => {
            currentMode = 'summary';
            document.getElementById('summaryBtn').classList.add('active');
            document.getElementById('quizBtn').classList.remove('active');
            document.getElementById('queryInput').placeholder = 'Ask a question or request a summary...';
        });

        document.getElementById('quizBtn').addEventListener('click', () => {
            currentMode = 'quiz';
            document.getElementById('quizBtn').classList.add('active');
            document.getElementById('summaryBtn').classList.remove('active');
            document.getElementById('queryInput').placeholder = 'What topic do you want to be quizzed on?';
        });

        // --- Submit question ---
        document.getElementById('submitBtn').addEventListener('click', async () => {
            const input = document.getElementById('queryInput');
            const question = input.value.trim();
            const responseArea = document.getElementById('responseArea');

            if (!question) {
                responseArea.innerHTML = '<div class="error">Please type a question or topic first.</div>';
                return;
            }

            currentQuestion = question;
            responseArea.innerHTML = '<div class="loading">Thinking with your slides... ⏳</div>';
            document.getElementById('submitBtn').disabled = true;

            try {
                const res = await fetch('/query', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ query: question, mode: currentMode })
                });

                const data = await res.json();

                if (!res.ok || data.error) {
                    responseArea.innerHTML = `<div class="error">❌ ${data.error || 'Request failed'}</div>`;
                    return;
                }

                let html = `<div class="response-box ${currentMode === 'quiz' ? 'quiz' : ''}">`;
                html += `<strong>${currentMode === 'quiz' ? '🎯 Quiz Question:' : '📝 Summary:'}</strong><br><br>`;
                html += data.response.replace(/\\n/g, '<br>');
                html += '</div>';

                if (currentMode === 'quiz') {
                    html += '<button class="forfeit-btn" onclick="forfeit()">❌ Forfeit & Show Answer</button>';
                }

                if (typeof data.latency_ms === 'number') {
                    html += `<p style="color: #999; font-size: 0.8em; margin-top: 10px;">⚡ Responded in ${data.latency_ms}ms</p>`;
                }

                responseArea.innerHTML = html;
            } catch (err) {
                responseArea.innerHTML = `<div class="error">❌ Request failed: ${err.message}</div>`;
            } finally {
                document.getElementById('submitBtn').disabled = false;
            }
        });

        // Enter key submits
        document.getElementById('queryInput').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                document.getElementById('submitBtn').click();
            }
        });

        // --- Forfeit quiz ---
        async function forfeit() {
            const responseArea = document.getElementById('responseArea');

            if (!currentQuestion) {
                responseArea.innerHTML = '<div class="error">No quiz question to forfeit.</div>';
                return;
            }

            responseArea.innerHTML += '<div class="loading">Revealing the answer... ⏳</div>';

            try {
                const res = await fetch('/forfeit', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ question: currentQuestion })
                });

                const data = await res.json();

                if (!res.ok || data.error) {
                    responseArea.innerHTML += `<div class="error">❌ ${data.error || 'Failed to get answer'}</div>`;
                    return;
                }

                let html = '<div class="response-box quiz">';
                html += '<strong>✅ Answer & Explanation:</strong><br><br>';
                html += data.answer.replace(/\\n/g, '<br>');
                html += '</div>';

                if (typeof data.latency_ms === 'number') {
                    html += `<p style="color: #999; font-size: 0.8em; margin-top: 10px;">⚡ Responded in ${data.latency_ms}ms</p>`;
                }

                responseArea.innerHTML += html;
            } catch (err) {
                responseArea.innerHTML += `<div class="error">❌ Request failed: ${err.message}</div>`;
            }
        }

        window.forfeit = forfeit;
        refreshStatus();
    </script>
</body>
</html>
"""


if __name__ == "__main__":
    print("🚀 Starting RecallAI...")
    print("📚 Upload your lecture PDFs and start studying!")
    print("🌐 Open http://localhost:5000 in your browser")
    app.run(debug=True, port=5000)
