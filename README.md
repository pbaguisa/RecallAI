# 🔃 RecallAI

> RAG-powered study assistant for active recall and quiz-based learning

RecallAI helps students master large volumes of lecture slides through AI-powered summaries and active recall testing. Upload your PDFs, get intelligent summaries, and quiz yourself on the material.

## 🎯 Features

- **📝 Summary Mode**: Get organized summaries of lecture topics with key concepts
- **🎯 Quiz Mode**: Test your understanding with AI-generated questions from your slides
- **❌ Forfeit & Learn**: Can't answer? Get the answer with detailed explanations
- **🔍 RAG-Powered**: Retrieves relevant content from your actual lecture slides
- **🛡️ Safety Checks**: Prompt injection detection and input validation
- **📊 Telemetry**: Tracks latency, tokens, and costs for every request

## 🚀 Quick Start

### Prerequisites

- Python 3.9 or higher
- Gemini API key (free tier available)

### Installation

1. **Clone the repository**
```bash
git clone <your-repo-url>
cd recallai
```

2. **Create virtual environment**
```bash
python -m venv venv

# On macOS/Linux:
source venv/bin/activate

# On Windows:
venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Set up environment variables**
```bash
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY
```

To get a Gemini API key:
1. Go to https://makersuite.google.com/app/apikey
2. Click "Create API Key"
3. Copy and paste into `.env`

5. **Create required directories**
```bash
mkdir -p uploads data
```

### Running the App

**One-command start:**
```bash
python app.py
```

Then open your browser to: **http://localhost:5000**

## 📖 Usage

### 1. Upload Lecture PDFs

- Click the upload zone on the homepage
- Select one or more PDF files (max 10 PDFs, 50 pages each)
- Wait for processing confirmation

### 2. Choose Your Mode

**Summary Mode**: Ask questions or request summaries
```
"Summarize neural networks"
"What is gradient descent?"
"Explain backpropagation"
```

**Quiz Mode**: Get tested on concepts
```
"Quiz me on neural networks"
"Test my knowledge of optimization"
"Give me a question about overfitting"
```

### 3. Study!

- Read summaries to understand concepts
- Answer quiz questions to test yourself
- Use "Forfeit & Show Answer" when stuck
- Review explanations to learn

## 🧪 Running Tests

### Automated Tests (Validation & Safety)

```bash
python run_tests.py
```

This runs 8 automated tests that check:
- Input validation (empty input, too long)
- Safety checks (prompt injection, academic dishonesty)
- Edge cases (off-topic queries)

**Expected output:**
```
🧪 RecallAI Test Suite

Running 8 validation & safety tests...
✓ Test 15: PASS - edge_case
✓ Test 16: PASS - edge_case
...

TEST SUMMARY
Validation & Safety Tests: 8/8 passed (100.0%)
```

### Manual Tests (Summary & Quiz)

Tests 1-14 require the app to be running with PDFs loaded:

1. Start the app: `python app.py`
2. Upload sample PDFs from `data/` folder
3. Try each test query from `tests.json`
4. Verify responses contain expected keywords

## 📊 Project Structure

```
recallai/
├── app.py              # Main Flask application
├── rag.py              # RAG system (embeddings + retrieval)
├── utils.py            # Utility functions (validation, PDF extraction)
├── requirements.txt    # Python dependencies
├── .env.example        # Environment variables template
├── tests.json          # Test suite (20 test cases)
├── run_tests.py        # Test runner script
├── README.md           # This file
├── uploads/            # User-uploaded PDFs (created at runtime)
├── data/               # Seed PDFs for testing
└── telemetry.jsonl     # Request logs (created at runtime)
```

## 🛡️ Safety & Robustness

### System Prompt
Instructs the LLM to:
- Answer only from lecture content
- Cite sources
- Refuse academic dishonesty
- Generate appropriate quiz questions

### Input Validation
- Max query length: 500 characters
- Max PDF size: 50 pages per file
- Max uploads: 10 PDFs total
- Checks for empty/invalid input

### Prompt Injection Detection
Blocks patterns like:
- "Ignore previous instructions"
- "Give me exam answers"
- "Override system prompt"

### Error Handling
- PDF extraction failures
- LLM API errors
- Missing documents
- Rate limiting

## 📈 Telemetry

Every request is logged to `telemetry.jsonl`:

```json
{
  "timestamp": "2024-11-23T14:32:01",
  "mode": "quiz",
  "pathway": "RAG",
  "query": "Quiz me on neural networks",
  "latency_ms": 1250,
  "tokens": 340,
  "cost_usd": 0.0,
  "metadata": {"chunks_retrieved": 3}
}
```

**Analyze logs:**
```python
import json
import pandas as pd

logs = []
with open("telemetry.jsonl") as f:
    for line in f:
        logs.append(json.loads(line))

df = pd.DataFrame(logs)
print(f"Average latency: {df['latency_ms'].mean():.0f}ms")
print(f"Total requests: {len(df)}")
print(f"Mode breakdown:\n{df['mode'].value_counts()}")
```

## 🎓 Assignment Requirements Checklist

### Core Feature ✅
- [x] Real user flow with LLM integration
- [x] Upload PDFs → RAG → Query → Response

### Enhancement: RAG ✅
- [x] Sentence-transformers embeddings
- [x] ChromaDB vector storage
- [x] Top-3 chunk retrieval
- [x] Metadata tracking (source files)

### Safety & Robustness ✅
- [x] System prompt with DO/DON'T rules
- [x] Input length guard (500 chars)
- [x] Prompt injection detection
- [x] Error fallback messages

### Telemetry ✅
- [x] Timestamp
- [x] Pathway (RAG)
- [x] Latency (ms)
- [x] Tokens
- [x] Cost (USD)

### Offline Evaluation ✅
- [x] 20 test cases in tests.json
- [x] Test runner script
- [x] Pass rate reporting
- [x] Categories: summary, quiz, edge_case, safety

### Documentation ✅
- [x] README.md with setup instructions
- [x] requirements.txt
- [x] .env.example
- [x] One-command run

## 🎨 Architecture

```
┌─────────────┐
│   User      │
└──────┬──────┘
       │ uploads PDF
       ▼
┌─────────────────┐
│  Flask App      │
│  (app.py)       │
└────────┬────────┘
         │
         ├─→ PDF Extraction (utils.py)
         │   └─→ PyPDF2
         │
         ├─→ RAG System (rag.py)
         │   ├─→ Chunk text (500 chars, 100 overlap)
         │   ├─→ Create embeddings (sentence-transformers)
         │   └─→ Store in ChromaDB
         │
         ├─→ Query Processing
         │   ├─→ Input validation (utils.py)
         │   ├─→ Safety checks (utils.py)
         │   ├─→ Retrieve context (rag.py)
         │   └─→ Call Gemini LLM
         │
         └─→ Telemetry Logging
             └─→ telemetry.jsonl
```

## 🔧 Configuration

### Chunk Size & Overlap
```python
# rag.py
self.chunk_size = 500       # characters per chunk
self.chunk_overlap = 100    # overlap between chunks
```

### Retrieval Settings
```python
# app.py
n_results = 3  # Top 3 most similar chunks
```

### Input Limits
```python
# utils.py
MAX_QUERY_LENGTH = 500   # characters
MAX_PDF_PAGES = 50       # per PDF
```

## 🐛 Troubleshooting

### "Module not found" errors
```bash
pip install -r requirements.txt
```

### "GEMINI_API_KEY not found"
1. Copy `.env.example` to `.env`
2. Add your API key to `.env`
3. Restart the app

### "Could not extract text from PDF"
- Ensure PDF contains readable text (not just images)
- Try a different PDF
- Check file isn't corrupted

### ChromaDB errors
```bash
pip uninstall chromadb
pip install chromadb==0.4.18
```

### Port 5000 already in use
```bash
# Use a different port
python app.py --port 5001
```

## 📝 Known Limitations

1. **Text-only PDFs**: Cannot extract text from image-based PDFs
2. **English only**: Works best with English content
3. **No conversation memory**: Each query is independent
4. **Small corpus**: Designed for 5-10 PDFs, not entire libraries
5. **Basic chunking**: Simple character-based chunking (could use semantic chunking)
6. **No user accounts**: All users share the same uploaded documents

## 🚀 Future Enhancements

- [ ] Image/diagram extraction from PDFs
- [ ] Multi-language support
- [ ] Conversation history/context
- [ ] User accounts and private document storage
- [ ] Spaced repetition algorithm
- [ ] Progress tracking and analytics
- [ ] Mobile app
- [ ] Export study materials

## 📄 License

MIT License - feel free to use for your coursework!

## 👤 Author

Patrick Baguisa

## 🙏 Acknowledgments

- Sentence Transformers for embeddings
- ChromaDB for vector storage
- Google Gemini for LLM capabilities
- Flask for web framework

---


**RecallAI: Your Lectures, Your Assessments, Your Victories.**


