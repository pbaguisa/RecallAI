"""
RecallAI - RAG-Powered Study Assistant
Main Flask Application
"""

from flask import Flask, request, jsonify, render_template_string
import os
import time
import json
import re
from datetime import datetime
from dotenv import load_dotenv
import google.generativeai as genai

from rag import RAGSystem
from utils import validate_input, check_safety, extract_pdf_text

# API Key
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))

load_dotenv()

# Init Flask
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB max file size
app.config["UPLOAD_FOLDER"] = "uploads"

# Create upload folder
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# Init Gemini, model: gemini-2.5-flash
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash")

# Init RAG
rag = RAGSystem()

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
        pass


def call_llm(prompt, context=""):
    """Call Gemini LLM with optional context."""
    full_prompt = f"{SYSTEM_PROMPT}\n\n"

    if context:
        full_prompt += f"Lecture Content:\n{context}\n\n"

    full_prompt += f"User Query: {prompt}"

    response = model.generate_content(full_prompt)

    # Approx token
    tokens = len(full_prompt.split()) + len((response.text or "").split())
    cost = 0.0  # Free tier lol

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
        # Shows the error in browser for flexibility
        return jsonify({"error": f"Error processing PDF: {str(e)}"}), 500


@app.route("/query", methods=["POST"])
def query():
    """Handle user queries (summary or quiz mode)."""
    start_time = time.time()

    data = request.get_json(force=True, silent=True) or {}
    user_query = data.get("query", "")
    mode = data.get("mode", "summary")  # Summary vs Quiz
    quiz_type = data.get("quiz_type", "")  # MC or Short Answer

    # Validate input
    if user_query:
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

        if mode == "quiz" and not user_query:
            # Get a random chunk from the RAG system
            all_chunks = rag.get_all_chunks()
            if not all_chunks:
                return jsonify({"error": "No content available for quiz generation."}), 400
            
            # Select a random chunk
            import random
            random_chunk = random.choice(all_chunks)
            context = random_chunk["text"]
            sources = [random_chunk["source"]]
        else:
            # Retrieve relevant context from RAG system
            context_chunks = rag.retrieve(user_query, n_results=3)
            if not context_chunks:
                return jsonify({"error": "Couldn't find relevant information in your slides. Try rephrasing your question."}), 404

            context = "\n\n".join(context_chunks)
            sources = rag.get_sources(user_query)

        # Modify prompt based on mode and quiz type
        if mode == "quiz":
            if quiz_type == "multiple_choice":
                prompt = (
                    "Generate ONE multiple choice question based on the provided lecture content.\n\n"
                    "The question should test understanding of the concepts in the "
                    "provided lecture content. Make it specific and answerable from the slides.\n\n"
                    "IMPORTANT: Format your response as valid JSON with the following structure:\n"
                    "{\n"
                    "  \"question\": \"Your question here\",\n"
                    "  \"options\": [\"Option A\", \"Option B\", \"Option C\", \"Option D\"],\n"
                    "  \"correct_answer\": \"A\",\n"
                    "  \"explanation\": \"Explanation of why this is the correct answer\"\n"
                    "}\n"
                    "Make sure only one option is correct and the explanation references the lecture content."
                )
            elif quiz_type == "short_answer":
                prompt = (
                    "Generate ONE fill-in-the-blank question based on the provided lecture content.\n\n"
                    "The question should test understanding of the concepts in the "
                    "provided lecture content. Make it specific and answerable from the slides.\n\n"
                    "IMPORTANT: Format your response as valid JSON with the following structure:\n"
                    "{\n"
                    "  \"question\": \"Your question with a blank marked as ____\",\n"
                    "  \"answer\": \"The correct answer for the blank\",\n"
                    "  \"explanation\": \"Explanation of why this is the correct answer\"\n"
                    "}\n"
                    "Make sure the answer is directly supported by the lecture content."
                )
            else:
                # Default to og quiz behaviour
                prompt = (
                    "Generate ONE quiz question based on the provided lecture content.\n\n"
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
            {"chunks_retrieved": len(context_chunks) if 'context_chunks' in locals() else 1},
        )

        # Parse JSON response for quiz types
        if mode == "quiz" and quiz_type in ["multiple_choice", "short_answer"]:
            try:
                # Extract JSON from the response
                json_match = re.search(r'({.*})', response, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1)
                    quiz_data = json.loads(json_str)
                    return jsonify({
                        "response": quiz_data,
                        "mode": mode,
                        "quiz_type": quiz_type,
                        "sources": sources,
                        "latency_ms": int((time.time() - start_time) * 1000),
                    })
                else:
                    # If no JSON found, return the raw response with a flag
                    return jsonify({
                        "response": response,
                        "mode": mode,
                        "quiz_type": quiz_type,
                        "is_valid_json": False,
                        "sources": sources,
                        "latency_ms": int((time.time() - start_time) * 1000),
                    })
            except json.JSONDecodeError as e:
                print(f"JSON decode error: {e}")  # Debug the JSON parsing error
                # If JSON parsing fails, return the raw response with a flag
                return jsonify({
                    "response": response,
                    "mode": mode,
                    "quiz_type": quiz_type,
                    "is_valid_json": False,
                    "sources": sources,
                    "latency_ms": int((time.time() - start_time) * 1000),
                })
        else:
            return jsonify({
                "response": response,
                "mode": mode,
                "sources": sources,
                "latency_ms": int((time.time() - start_time) * 1000),
            })

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


@app.route("/validate_answer", methods=["POST"])
def validate_answer():
    """Validate short answer quiz responses."""
    start_time = time.time()

    data = request.get_json(force=True, silent=True) or {}
    question = data.get("question", "")
    user_answer = data.get("answer", "").strip()
    correct_answer = data.get("correct_answer", "").strip()

    try:
        # First, do a case-insensitive exact match check
        if user_answer.lower() == correct_answer.lower():
            log_request(question, "validate_answer", "RAG", start_time, 0, 0)
            return jsonify({
                "validation": {
                    "correct": True,
                    "feedback": f"Correct! '{user_answer}' matches the expected answer."
                },
                "latency_ms": int((time.time() - start_time) * 1000),
            })

        # Retrieve context for the question
        context_chunks = rag.retrieve(question, n_results=2)
        context = "\n\n".join(context_chunks)

        # Get validation from LLM for more complex matching
        prompt = (
            f"Question: {question}\n\n"
            f"Correct answer: {correct_answer}\n\n"
            f"Student's answer: {user_answer}\n\n"
            "Determine if the student's answer is correct or equivalent to the correct answer. "
            "Consider synonyms, alternative phrasing, partial credit, and case-insensitive matching. "
            "Case should not matter - 'Answer', 'answer', and 'ANSWER' are all equivalent. "
            "IMPORTANT: Respond ONLY with valid JSON in this exact format: "
            "{{\"correct\": true or false, \"feedback\": \"brief explanation\"}}"
        )
        response, tokens, cost = call_llm(prompt, context)

        # Try to extract JSON from the response
        validation_result = None
        try:
            # First try to parse the entire response as JSON
            validation_result = json.loads(response)
        except json.JSONDecodeError:
            # Try to find JSON object in the response 
            json_match = re.search(r'(\{.*\})', response, re.DOTALL)
            if json_match:
                try:
                    json_str = json_match.group(1)
                    validation_result = json.loads(json_str)
                    # Verify it has the "correct" field
                    if "correct" not in validation_result:
                        validation_result = None
                except json.JSONDecodeError:
                    pass

        if validation_result and "correct" in validation_result:
            # Ensure correct is a boolean
            validation_result["correct"] = bool(validation_result["correct"])
            if "feedback" not in validation_result:
                validation_result["feedback"] = "Answer validated."
            log_request(question, "validate_answer", "RAG", start_time, tokens, cost)
            return jsonify({
                "validation": validation_result,
                "latency_ms": int((time.time() - start_time) * 1000),
            })
        else:
            # Fallback: case-insensitive comparison if LLM failed
            is_correct = user_answer.lower() == correct_answer.lower()
            log_request(question, "validate_answer", "RAG", start_time, tokens, cost)
            return jsonify({
                "validation": {
                    "correct": is_correct,
                    "feedback": "Validated using direct comparison." if is_correct else f"Your answer '{user_answer}' does not match '{correct_answer}'."
                },
                "latency_ms": int((time.time() - start_time) * 1000),
            })

    except Exception as e:
        # Final fallback: case-insensitive comparison
        is_correct = user_answer.lower() == correct_answer.lower() if user_answer and correct_answer else False
        log_request(question, "validate_answer", "RAG", start_time, 0, 0, {"error": str(e)})
        return jsonify({
            "validation": {
                "correct": is_correct,
                "feedback": "Validated using direct comparison." if is_correct else f"Your answer '{user_answer}' does not match '{correct_answer}'."
            },
            "latency_ms": int((time.time() - start_time) * 1000),
        })


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
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Space+Grotesk:wght@500&display=swap');
        :root {
            --bg: #0a0a0a;
            --bg-alt: #121212;
            --card: #1a1a1a;
            --card-alt: #222222;
            --accent: #b8bcc8;
            --accent-strong: #d4d8e4;
            --accent-soft: rgba(184, 188, 200, 0.1);
            --text: #f2f4ff;
            --muted: #a0a0a0;
            --border: rgba(255, 255, 255, 0.08);
            --warning: #f4c27f;
            --error-bg: rgba(255, 99, 132, 0.12);
            --error-text: #ff708d;
            --success-bg: rgba(104, 211, 145, 0.12);
            --success-text: #7fd8a6;
        }
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: radial-gradient(circle at top, #1a1a1a 0%, #0f0f0f 45%, #0a0a0a 100%);
            color: var(--text);
            min-height: 100vh;
            padding: 32px 20px 60px;
        }
        .container {
            max-width: 920px;
            margin: 0 auto;
        }
        .header {
            background: linear-gradient(145deg, #1a1a1a, #222222);
            border-radius: 20px;
            padding: 36px;
            margin-bottom: 24px;
            border: 1px solid var(--border);
            box-shadow: 0 20px 50px rgba(0, 0, 0, 0.6);
        }
        .header h1 {
            font-family: 'Space Grotesk', 'Inter', sans-serif;
            color: var(--text);
            font-size: 2.4em;
            margin-bottom: 12px;
            letter-spacing: 0.02em;
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .logo {
            width: 1.2em;
            height: 1.2em;
            display: inline-block;
        }
        .sr-only {
            position: absolute;
            width: 1px;
            height: 1px;
            padding: 0;
            margin: -1px;
            overflow: hidden;
            clip: rect(0, 0, 0, 0);
            border: 0;
        }
        .header p {
            color: var(--muted);
            font-size: 1.05em;
            line-height: 1.5;
        }
        .card {
            background: linear-gradient(160deg, rgba(20, 20, 20, 0.85), rgba(26, 26, 26, 0.95));
            border-radius: 18px;
            padding: 28px;
            margin-bottom: 22px;
            border: 1px solid var(--border);
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.55);
        }
        .card h2 {
            font-family: 'Space Grotesk', 'Inter', sans-serif;
            color: var(--text);
            font-size: 1.35em;
            margin-bottom: 18px;
        }
        .upload-zone {
            border: 2px dashed rgba(184, 188, 200, 0.5);
            border-radius: 14px;
            padding: 42px;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s ease;
            background: rgba(15, 15, 15, 0.6);
            color: var(--muted);
        }
        .upload-zone:hover {
            background: rgba(184, 188, 200, 0.08);
            border-color: var(--accent);
            transform: translateY(-2px);
        }
        .upload-zone input {
            display: none;
        }
        .btn {
            background: linear-gradient(120deg, #c8ccd8, #b0b4c0);
            color: #0a0a0a;
            border: none;
            padding: 14px 26px;
            border-radius: 12px;
            cursor: pointer;
            font-size: 1em;
            font-weight: 600;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
            box-shadow: 0 12px 25px rgba(180, 184, 196, 0.25);
        }
        .btn:hover {
            background: linear-gradient(120deg, #d4d8e4, #c0c4d0);
            transform: translateY(-2px) scale(1.01);
            box-shadow: 0 15px 35px rgba(180, 184, 196, 0.35);
        }
        .btn:disabled {
            background: rgba(184, 188, 200, 0.25);
            color: rgba(255, 255, 255, 0.4);
            cursor: not-allowed;
            box-shadow: none;
            transform: none;
        }
        .mode-toggle {
            display: flex;
            gap: 12px;
            margin-bottom: 24px;
        }
        .mode-btn {
            flex: 1;
            padding: 14px;
            border: 1px solid var(--border);
            background: rgba(18, 18, 18, 0.8);
            color: var(--muted);
            border-radius: 14px;
            cursor: pointer;
            font-size: 1em;
            font-weight: 600;
            transition: all 0.3s ease;
        }
        .mode-btn.active {
            background: var(--accent-soft);
            border-color: rgba(184, 188, 200, 0.6);
            color: var(--text);
            box-shadow: inset 0 0 35px rgba(180, 184, 196, 0.15);
        }
        .quiz-type-toggle {
            display: flex;
            gap: 12px;
            margin-bottom: 24px;
        }
        .quiz-type-btn {
            flex: 1;
            padding: 14px;
            border: 1px solid var(--border);
            background: rgba(18, 18, 18, 0.8);
            color: var(--muted);
            border-radius: 14px;
            cursor: pointer;
            font-size: 1em;
            font-weight: 600;
            transition: all 0.3s ease;
        }
        .quiz-type-btn:hover {
            background: var(--accent-soft);
            border-color: rgba(184, 188, 200, 0.6);
            color: var(--text);
        }
        .query-input {
            width: 100%;
            padding: 18px;
            border: 1px solid var(--border);
            border-radius: 16px;
            font-size: 1em;
            margin-bottom: 18px;
            background: rgba(15, 15, 15, 0.6);
            color: var(--text);
            transition: border 0.2s ease, box-shadow 0.2s ease;
        }
        .query-input::placeholder {
            color: rgba(255, 255, 255, 0.4);
        }
        .query-input:focus {
            outline: none;
            border-color: rgba(184, 188, 200, 0.7);
            box-shadow: 0 0 0 3px rgba(180, 184, 196, 0.15);
        }
        .response-box {
            background: rgba(12, 12, 12, 0.85);
            border-radius: 18px;
            padding: 24px;
            margin-top: 24px;
            min-height: 110px;
            border: 1px solid var(--border);
            line-height: 1.6;
        }
        .response-box.quiz {
            background: rgba(43, 27, 7, 0.6);
            border-color: rgba(244, 194, 127, 0.4);
        }
        .forfeit-btn {
            background: linear-gradient(120deg, #ff7c96, #ff5175);
            color: white;
            border: none;
            padding: 11px 22px;
            border-radius: 12px;
            cursor: pointer;
            margin-top: 18px;
            font-weight: 600;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }
        .forfeit-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 12px 30px rgba(255, 112, 141, 0.3);
        }
        .loading {
            text-align: center;
            color: var(--accent);
            font-size: 1.05em;
            padding: 20px;
        }
        .error {
            background: var(--error-bg);
            color: var(--error-text);
            padding: 15px;
            border-radius: 12px;
            margin-top: 18px;
            border: 1px solid rgba(255, 112, 141, 0.3);
        }
        .success {
            background: var(--success-bg);
            color: var(--success-text);
            padding: 15px;
            border-radius: 12px;
            margin-top: 18px;
            border: 1px solid rgba(127, 216, 166, 0.3);
        }
        .files-list {
            margin-top: 18px;
        }
        .file-item {
            background: rgba(18, 18, 18, 0.8);
            padding: 12px;
            border-radius: 10px;
            margin-bottom: 10px;
            border: 1px solid var(--border);
            color: var(--muted);
        }
        .quiz-option {
            margin: 10px 0;
            display: flex;
            align-items: center;
        }
        .quiz-option input {
            margin-right: 10px;
        }
        .quiz-option label {
            cursor: pointer;
        }
        .quiz-result {
            margin-top: 20px;
            padding: 15px;
            border-radius: 12px;
        }
        .quiz-result.correct {
            background: var(--success-bg);
            color: var(--success-text);
            border: 1px solid rgba(127, 216, 166, 0.3);
        }
        .quiz-result.incorrect {
            background: var(--error-bg);
            color: var(--error-text);
            border: 1px solid rgba(255, 112, 141, 0.3);
        }
        .debug-info {
            background: rgba(100, 100, 100, 0.2);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            padding: 10px;
            margin-top: 10px;
            font-family: monospace;
            font-size: 0.8em;
            color: #ccc;
            max-height: 150px;
            overflow-y: auto;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>
                <svg class="logo" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 80" width="80" height="80">
                    <defs>
                        <linearGradient id="silverGradientIconTrimmed" x1="0%" y1="0%" x2="100%" y2="100%">
                            <stop offset="0%" stop-color="#B0B0B0" />
                            <stop offset="100%" stop-color="#FFFFFF" />
                        </linearGradient>
                    </defs>
                    <g transform="translate(0, 0)">
                        <animateTransform attributeName="transform" type="rotate" from="0 40 40" to="360 40 40" dur="8s" repeatCount="indefinite"/>
                        <path d="M 5,40 A 35,35 0 0,1 60,20" 
                              fill="none" stroke="url(#silverGradientIconTrimmed)" stroke-width="8" stroke-linecap="round" />
                        <path d="M 48,10 L 60,20 L 48,30" 
                              fill="none" stroke="url(#silverGradientIconTrimmed)" stroke-width="8" stroke-linecap="round" stroke-linejoin="round" />
                        <path d="M 75,40 A 35,35 0 0,1 20,60" 
                              fill="none" stroke="url(#silverGradientIconTrimmed)" stroke-width="8" stroke-linecap="round" />
                        <path d="M 32,50 L 20,60 L 32,70" 
                              fill="none" stroke="url(#silverGradientIconTrimmed)" stroke-width="8" stroke-linecap="round" stroke-linejoin="round" />
                    </g>
                </svg>
                RecallAI
            </h1>
            <p>Study smarter with AI-powered summaries and testing</p>
            <p id="statusText" style="margin-top: 8px; color: var(--muted); font-size: 0.9em;"></p>
        </div>

        <div class="card">
            <h2>Step 1: Upload Lecture PDFs</h2>
            <div class="upload-zone" onclick="document.getElementById('fileInput').click()">
                <input type="file" id="fileInput" accept=".pdf" multiple>
                <p>📄 Click to upload PDF files</p>
                <p style="color: #999; font-size: 0.9em;">Maximum 10 PDFs, 100 pages each</p>
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

            <div id="querySection">
                <!-- This will be replaced based on the mode -->
            </div>

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

        // --- Initialize with summary mode ---
        document.addEventListener('DOMContentLoaded', () => {
            // Initialize with summary mode
            document.getElementById('querySection').innerHTML = `
                <input type="text" id="queryInput" class="query-input" placeholder="Ask a question or request a summary...">
                <button class="btn" id="submitBtn">Ask RecallAI</button>
            `;
            
            // Attach event listeners
            document.getElementById('submitBtn').addEventListener('click', submitQuery);
            document.getElementById('queryInput').addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    document.getElementById('submitBtn').click();
                }
            });
            
            // Mode toggle listeners
            document.getElementById('summaryBtn').addEventListener('click', () => {
                currentMode = 'summary';
                document.getElementById('summaryBtn').classList.add('active');
                document.getElementById('quizBtn').classList.remove('active');
                document.getElementById('querySection').innerHTML = `
                    <input type="text" id="queryInput" class="query-input" placeholder="Ask a question or request a summary...">
                    <button class="btn" id="submitBtn">Ask RecallAI</button>
                `;
                // Re-attach event listeners
                document.getElementById('submitBtn').addEventListener('click', submitQuery);
                document.getElementById('queryInput').addEventListener('keypress', (e) => {
                    if (e.key === 'Enter') {
                        e.preventDefault();
                        document.getElementById('submitBtn').click();
                    }
                });
            });
            
            document.getElementById('quizBtn').addEventListener('click', () => {
                currentMode = 'quiz';
                document.getElementById('quizBtn').classList.add('active');
                document.getElementById('summaryBtn').classList.remove('active');
                document.getElementById('querySection').innerHTML = `
                    <div class="quiz-type-toggle">
                        <button class="quiz-type-btn" id="multipleChoiceBtn">🔘 Multiple Choice</button>
                        <button class="quiz-type-btn" id="shortAnswerBtn">✍️ Short Answer</button>
                    </div>
                `;
                // Re-attach event listeners
                document.getElementById('multipleChoiceBtn').addEventListener('click', () => {
                    generateQuiz('multiple_choice');
                });
                document.getElementById('shortAnswerBtn').addEventListener('click', () => {
                    generateQuiz('short_answer');
                });
            });
            
            // Event delegation for regenerate button (works even after DOM changes)
            const responseArea = document.getElementById('responseArea');
            if (responseArea) {
                responseArea.addEventListener('click', (e) => {
                    // Check if the clicked element is the regenerate button or inside it
                    let target = e.target;
                    while (target && target !== responseArea) {
                        if (target.id === 'regenerateBtn') {
                            e.preventDefault();
                            regenerateQuiz();
                            return;
                        }
                        target = target.parentElement;
                    }
                });
            }
        });

        // --- Regenerate quiz (uses stored quiz type) ---
        function regenerateQuiz() {
            if (window.currentQuiz && window.currentQuiz.type) {
                generateQuiz(window.currentQuiz.type);
            } else {
                // Default to multiple choice if no type stored
                generateQuiz('multiple_choice');
            }
        }

        // --- Generate quiz ---
        let isGeneratingQuiz = false;
        let abortController = null;
        async function generateQuiz(quizType) {
            // Cancel any in-flight requests
            if (abortController) {
                abortController.abort();
            }
            
            // Prevent multiple simultaneous quiz generations
            if (isGeneratingQuiz) {
                return;
            }
            
            // Create a new AbortController for this request
            abortController = new AbortController();
            
            const responseArea = document.getElementById('responseArea');
            // Clear immediately to prevent showing old content
            responseArea.innerHTML = '';
            
            // Small delay to ensure DOM is cleared
            await new Promise(resolve => setTimeout(resolve, 10));
            
            responseArea.innerHTML = '<div class="loading">Generating quiz question... ⏳</div>';
            isGeneratingQuiz = true;

            try {
                const res = await fetch('/query', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        query: '',  // Empty query for random quiz generation
                        mode: 'quiz',
                        quiz_type: quizType
                    }),
                    signal: abortController.signal
                });

                const data = await res.json();

                if (!res.ok || data.error) {
                    responseArea.innerHTML = `<div class="error">❌ ${data.error || 'Request failed'}</div>`;
                    return;
                }

                // Debug: Log the response
                console.log('Server response:', data);

                // Check if the response is valid JSON
                if (data.is_valid_json === false) {
                    responseArea.innerHTML = `
                        <div class="error">❌ The AI didn't return a valid format. Please try again.</div>
                        <div class="debug-info">
                            <strong>Debug info:</strong><br>
                            ${JSON.stringify(data, null, 2)}
                        </div>
                    `;
                    return;
                }

                if (quizType === 'multiple_choice') {
                    displayMultipleChoiceQuiz(data.response);
                } else if (quizType === 'short_answer') {
                    displayShortAnswerQuiz(data.response);
                }
            } catch (err) {
                // Ignore aborted requests
                if (err.name === 'AbortError') {
                    return;
                }
                responseArea.innerHTML = `<div class="error">❌ Request failed: ${err.message}</div>`;
            } finally {
                isGeneratingQuiz = false;
                abortController = null;
            }
        }

        // --- Display multiple choice quiz ---
        function displayMultipleChoiceQuiz(quizData) {
            const responseArea = document.getElementById('responseArea');
            
            // Clear the response area immediately to prevent showing old content
            responseArea.innerHTML = '';
            
            // Debug: Log the quiz data
            console.log('Quiz data:', quizData);
            
            // Check if quizData has the expected structure
            if (!quizData || !quizData.question || !quizData.options || !quizData.correct_answer) {
                responseArea.innerHTML = `
                    <div class="error">❌ Invalid quiz format received</div>
                    <div class="debug-info">
                        <strong>Debug info:</strong><br>
                        ${JSON.stringify(quizData, null, 2)}
                    </div>
                `;
                return;
            }

            // Normalize options to remove any existing A/B/C/D prefixes
            const normalizedOptions = quizData.options.map((option, index) => {
                if (typeof option !== 'string') {
                    return String(option ?? '');
                }
                const trimmed = option.trim();
                // Remove patterns like "A. ", "B) ", "C ", etc.
                const sanitized = trimmed.replace(/^[A-D][\.\)]?\s+/i, '').trim();
                return sanitized.length > 0 ? sanitized : trimmed;
            });

            let html = `<div class="response-box quiz">`;
            html += `<strong>🎯 Quiz Question:</strong><br><br>`;
            html += `<p>${quizData.question}</p><br>`;
            
            // Create options with radio buttons
            normalizedOptions.forEach((option, index) => {
                const optionLetter = String.fromCharCode(65 + index); // A, B, C, D
                html += `
                    <div class="quiz-option">
                        <input type="radio" id="option${optionLetter}" name="quizOption" value="${optionLetter}">
                        <label for="option${optionLetter}">${optionLetter}. ${option}</label>
                    </div>
                `;
            });
            
            html += `<br>`;
            html += `<button class="btn" id="submitAnswerBtn">Submit Answer</button>`;
            html += `<button class="btn" id="regenerateBtn" style="margin-left: 10px;"> Next Question ➡️ </button>`;
            html += `</div>`;
            
            responseArea.innerHTML = html;
            
            // Store quiz data for validation (with normalized options)
            const normalizedQuizData = {
                ...quizData,
                options: normalizedOptions
            };
            window.currentQuiz = {
                type: 'multiple_choice',
                data: normalizedQuizData
            };
            
            // Add event listeners
            document.getElementById('submitAnswerBtn').addEventListener('click', () => {
                const selectedOption = document.querySelector('input[name="quizOption"]:checked');
                if (!selectedOption) {
                    alert('Please select an answer');
                    return;
                }
                
                // Case-insensitive comparison for multiple choice
                const isCorrect = selectedOption.value.toUpperCase() === quizData.correct_answer.toUpperCase();
                const resultHtml = `
                    <div class="quiz-result ${isCorrect ? 'correct' : 'incorrect'}">
                        <strong>${isCorrect ? '✅ Correct!' : '❌ Incorrect'}</strong><br><br>
                        <p>The correct answer is: <strong>${quizData.correct_answer.toUpperCase()}. ${normalizedOptions[quizData.correct_answer.toUpperCase().charCodeAt(0) - 65]}</strong></p>
                        <p>${quizData.explanation || 'No explanation provided.'}</p>
                    </div>
                `;
                
                responseArea.innerHTML += resultHtml;
                document.getElementById('submitAnswerBtn').disabled = true;
            });
            
            // Use event delegation or ensure button is always clickable
            const regenerateBtn = document.getElementById('regenerateBtn');
            if (regenerateBtn) {
                regenerateBtn.onclick = regenerateQuiz;
            }
        }

        // --- Display short answer quiz ---
        function displayShortAnswerQuiz(quizData) {
            const responseArea = document.getElementById('responseArea');
            
            // Clear the response area immediately to prevent showing old content
            responseArea.innerHTML = '';
            
            // Debug: Log the quiz data
            console.log('Quiz data:', quizData);
            
            // Check if quizData has the expected structure
            if (!quizData || !quizData.question || !quizData.answer) {
                responseArea.innerHTML = `
                    <div class="error">❌ Invalid quiz format received</div>
                    <div class="debug-info">
                        <strong>Debug info:</strong><br>
                        ${JSON.stringify(quizData, null, 2)}
                    </div>
                `;
                return;
            }

            let html = `<div class="response-box quiz">`;
            html += `<strong>🎯 Quiz Question:</strong><br><br>`;
            html += `<p>${quizData.question}</p><br>`;
            html += `<input type="text" id="shortAnswerInput" class="query-input" placeholder="Type your answer here...">`;
            html += `<br><br>`;
            html += `<button class="btn" id="submitAnswerBtn">Submit Answer</button>`;
            html += `<button class="btn" id="regenerateBtn" style="margin-left: 10px;"> Next Question ➡️ </button>`;
            html += `</div>`;
            
            responseArea.innerHTML = html;
            
            // Store quiz data for validation
            window.currentQuiz = {
                type: 'short_answer',
                data: quizData
            };
            
            // Add event listeners
            document.getElementById('submitAnswerBtn').addEventListener('click', async () => {
                const userAnswer = document.getElementById('shortAnswerInput').value.trim();
                if (!userAnswer) {
                    alert('Please enter an answer');
                    return;
                }
                
                document.getElementById('submitAnswerBtn').disabled = true;
                responseArea.innerHTML += '<div class="loading">Validating answer... ⏳</div>';
                
                try {
                    const res = await fetch('/validate_answer', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ 
                            question: quizData.question,
                            answer: userAnswer,
                            correct_answer: quizData.answer
                        })
                    });
                    
                    const data = await res.json();
                    
                    if (!res.ok || data.error) {
                        responseArea.innerHTML += `<div class="error">❌ ${data.error || 'Validation failed'}</div>`;
                        return;
                    }
                    
                    const isCorrect = data.validation.correct;
                    const resultHtml = `
                        <div class="quiz-result ${isCorrect ? 'correct' : 'incorrect'}">
                            <strong>${isCorrect ? '✅ Correct!' : '❌ Incorrect'}</strong><br><br>
                            <p>Your answer: ${userAnswer}</p>
                            <p>Correct answer: <strong>${quizData.answer}</strong></p>
                            <p>${data.validation.feedback || 'No feedback provided.'}</p>
                            <p>${quizData.explanation || 'No explanation provided.'}</p>
                        </div>
                    `;
                    
                    responseArea.innerHTML += resultHtml;
                } catch (err) {
                    responseArea.innerHTML += `<div class="error">❌ Validation failed: ${err.message}</div>`;
                }
            });
            
            // Use event delegation or ensure button is always clickable
            const regenerateBtn = document.getElementById('regenerateBtn');
            if (regenerateBtn) {
                regenerateBtn.onclick = regenerateQuiz;
            }
        }

        // --- Submit question ---
        function submitQuery() {
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

            fetch('/query', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query: question, mode: currentMode })
            })
            .then(res => res.json())
            .then(data => {
                if (data.error) {
                    responseArea.innerHTML = `<div class="error">❌ ${data.error}</div>`;
                    return;
                }

                let html = `<div class="response-box">`;
                html += `<strong>📝 Summary:</strong><br><br>`;
                html += data.response.replace(/\\n/g, '<br>');
                html += '</div>';

                if (typeof data.latency_ms === 'number') {
                    html += `<p style="color: #999; font-size: 0.8em; margin-top: 10px;">⚡ Responded in ${data.latency_ms}ms</p>`;
                }

                responseArea.innerHTML = html;
            })
            .catch(err => {
                responseArea.innerHTML = `<div class="error">❌ Request failed: ${err.message}</div>`;
            })
            .finally(() => {
                document.getElementById('submitBtn').disabled = false;
            });
        }

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