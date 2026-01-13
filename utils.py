"""
RecallAI - Utility Functions
Input validation, safety checks, PDF extraction
"""

import PyPDF2
from typing import Dict

# Configuration
MAX_QUERY_LENGTH = 500
MAX_PDF_PAGES = 100

# Safety patterns
INJECTION_PATTERNS = [
    "ignore previous instructions",
    "ignore all instructions",
    "disregard the above",
    "you are now",
    "new instructions:",
    "forget everything",
    "system:",
    "override",
    "jailbreak",
    "give me the exam answers",
    "tell me what's on the test",
    "what questions will be on",
    "show me the test"
]

def validate_input(user_query: str) -> Dict:
    """
    Validate user input
    Returns: {"error": bool, "message": str}
    """
    # Check for empty input
    if not user_query or not user_query.strip():
        return {
            "error": True,
            "message": "Please enter a question or request."
        }
    
    # Check length
    if len(user_query) > MAX_QUERY_LENGTH:
        return {
            "error": True,
            "message": f"Query too long. Please keep it under {MAX_QUERY_LENGTH} characters."
        }
    
    return {"error": False}

def check_safety(user_input: str) -> Dict:
    """
    Check for prompt injection and unsafe inputs
    Returns: {"safe": bool, "message": str}
    """
    input_lower = user_input.lower()
    
    # Check for injection patterns
    for pattern in INJECTION_PATTERNS:
        if pattern in input_lower:
            return {
                "safe": False,
                "message": "⚠️ Invalid input detected. Please ask legitimate study questions without attempting prompt injection or requesting exam answers."
            }
    
    return {"safe": True}

def extract_pdf_text(filepath: str) -> str:
    """
    Extract text from PDF file
    Returns: Extracted text as string
    """
    try:
        text = ""
        
        with open(filepath, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            
            # Check page limit
            num_pages = len(pdf_reader.pages)
            if num_pages > MAX_PDF_PAGES:
                raise Exception(f"PDF has {num_pages} pages. Maximum allowed is {MAX_PDF_PAGES}.")
            
            # Extract text from each page
            for page_num in range(num_pages):
                page = pdf_reader.pages[page_num]
                page_text = page.extract_text()
                
                if page_text:
                    text += f"\n[Page {page_num + 1}]\n{page_text}"
        
        return text
    
    except Exception as e:
        raise Exception(f"Failed to extract text from PDF: {str(e)}")

def format_response(text: str) -> str:
    """
    Format LLM response for better readability
    """
    # Clean up extra whitespace
    text = ' '.join(text.split())
    
    # Add newlines before numbered lists
    text = text.replace('. 1.', '.\n\n1.')
    text = text.replace('. 2.', '.\n2.')
    text = text.replace('. 3.', '.\n3.')
    
    return text