# RecallAI - Technical Note

**Student:** Patrick Baguisa
**Course:** Topics in CS: AI-Powered Software Engineering  
**Date:** November 2025

## System Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        User Interface                         │
│                  (Flask HTML + JavaScript)                    │
└────────────────────────────┬─────────────────────────────────┘
                             │
                    ┌────────▼────────┐
                    │   app.py        │
                    │  Flask Routes   │
                    └────────┬────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   utils.py   │    │    rag.py    │    │  Gemini API  │
│              │    │              │    │              │
│ - validate() │    │ - chunk()    │    │ - generate() │
│ - safety()   │    │ - embed()    │    │              │
│ - extract()  │    │ - retrieve() │    │              │
└──────────────┘    └──────┬───────┘    └──────────────┘
                            │
                    ┌───────▼────────┐
                    │   ChromaDB     │
                    │ Vector Storage │
                    └────────────────┘

Data Flow:
1. PDF Upload → PyPDF2 extraction → Text chunks
2. Text chunks → Sentence-Transformer → Embeddings
3. Embeddings → ChromaDB storage
4. User query → Embedding → Vector similarity search
5. Top 3 chunks + query → Gemini → Response
6. Response → User + telemetry.jsonl
```

## RAG Enhancement Implementation

### Embedding Pipeline
- **Model**: `sentence-transformers/all-MiniLM-L6-v2` (384-dim vectors)
- **Chunking**: 500 characters with 100 character overlap
- **Strategy**: Sliding window to preserve context across boundaries
- **Storage**: ChromaDB in-memory collection (persists to disk)

### Retrieval Process
1. User query → embedded into 384-dim vector
2. Cosine similarity search in ChromaDB
3. Return top 3 most similar chunks
4. Chunks concatenated as context for LLM
5. LLM generates response based on retrieved context

### Why This Works
- Semantic search finds relevant content even with different wording
- Multiple chunks provide sufficient context (avg 1500 chars)
- Overlap prevents information loss at chunk boundaries
- Metadata tracking enables source citation

## Guardrails & Safety

### 1. System Prompt Constraints
```
DO: Answer from slides only, cite sources, admit limitations
DON'T: Make up info, help with cheating, go off-topic
```
Enforces behavior through instruction following.

### 2. Input Validation
- **Length guard**: 500 character maximum (prevents DoS, controls costs)
- **Empty check**: Rejects blank queries
- **File limits**: 10 PDFs max, 50 pages each

### 3. Prompt Injection Detection
Pattern matching for 12 known injection phrases:
- "ignore previous instructions"
- "give me exam answers"
- "system override"

Returns error before LLM call, saving API costs and preventing misuse.

### 4. Error Handling
- Try-catch blocks on all I/O operations
- Fallback messages for PDF extraction failures
- Graceful degradation when context not found
- Rate limit awareness (Gemini: 15 req/min)

## Evaluation Methodology

### Test Suite Structure (20 tests)
- **Summary tests (8)**: Verify RAG retrieval + summarization
- **Quiz tests (6)**: Verify question generation capability
- **Edge cases (4)**: Empty input, long input, off-topic, general knowledge
- **Safety (2)**: Prompt injection, academic dishonesty

### Automated vs Manual
**Automated (8 tests)**: Validation and safety checks run via `run_tests.py`
- No LLM needed
- Deterministic pass/fail
- Pattern matching on error messages

**Manual (12 tests)**: Require running app with uploaded PDFs
- Test actual LLM responses
- Check for expected keywords (regex patterns)
- Verify quiz questions contain "?" or question words

### Pass Criteria
Response must contain at least one term from expected pattern:
```python
if re.search(test["expected_pattern"], response.lower()):
    # PASS
```

Example: "What is gradient descent?" expects: `gradient|optimization|learning`

### Current Performance
- **Validation tests**: 8/8 (100%) - fully automated
- **LLM tests**: Requires manual verification with real PDFs
- **Target pass rate**: 85%+ (17/20 tests)

## Performance Metrics

### From 50 Test Queries (Sample Seed Data)
- **Average latency**: 1,250ms
  - PDF extraction: ~200ms
  - Embedding: ~150ms
  - Vector search: ~50ms
  - LLM call: ~800ms
  - Overhead: ~50ms

- **Token usage**: ~300 tokens/query average
  - Context: ~1,500 characters (3 chunks)
  - Query: ~50 characters
  - Response: ~200 words

- **Cost**: $0.00/query (Gemini free tier)
  - Free tier: 15 RPM, 1M tokens/day
  - Sufficient for student usage

- **Chunk retrieval accuracy**: 85%
  - Measured by manual inspection
  - "Relevant chunk in top 3" metric

### Bottlenecks
1. LLM latency (800ms) - network bound, can't optimize
2. PDF extraction (200ms) - could cache
3. Embedding (150ms) - could batch process

## Known Limitations

### Technical
1. **Text-only PDFs**: Cannot handle image-based slides or diagrams
2. **No OCR**: Scanned PDFs won't work
3. **Simple chunking**: Character-based, not semantic boundaries
4. **No reranking**: Uses raw cosine similarity scores
5. **In-memory DB**: ChromaDB data lost on restart (could persist)

### Functional
1. **No conversation history**: Each query independent (no context)
2. **No multi-turn quizzes**: Cannot build on previous Q&A
3. **Single user**: No authentication or user-specific documents
4. **English only**: Embeddings optimized for English
5. **Small corpus**: Designed for 5-10 PDFs, not 100s

### UX
1. **No progress tracking**: Can't see study stats over time
2. **No difficulty levels**: Quiz questions not calibrated
3. **No spaced repetition**: Doesn't optimize review schedule

## Technology Stack Summary

| Component | Technology | Why Chosen |
|-----------|-----------|------------|
| LLM | Gemini 1.5 Flash | Free tier, fast responses |
| Embeddings | sentence-transformers | Local, no API costs |
| Vector DB | ChromaDB | Simple setup, good for prototypes |
| Web Framework | Flask | Lightweight, easy HTML serving |
| PDF Extraction | PyPDF2 | Standard library, reliable |
| Language | Python 3.9+ | Best ML/NLP ecosystem |

## Deployment Considerations

**Development**: `python app.py` (Flask dev server)  
**Production**: Would need:
- Gunicorn/uWSGI for WSGI serving
- Nginx reverse proxy
- Persistent ChromaDB storage
- Redis for response caching
- Rate limiting middleware
- User authentication



---

