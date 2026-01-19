import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pdf_engine import PDFEngine
from llm_controller import LLMController

# MOCK API KEY if not set (User should set this in env or I rely on what's available)
# The user seems to have one configured.
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    # Try loading from config
    config_path = os.path.join(os.path.expanduser("~"), ".bib_extractor_config.json")
    if os.path.exists(config_path):
        import json
        try:
            with open(config_path, "r") as f:
                api_key = json.load(f).get("api_key")
        except: pass

if not api_key:
    # Just warn, don't exit, so we can verify Context Extraction
    print("WARNING: No API Key found (Env or Config). Will verify Context Extraction ONLY.")


def test_bernevig():
    print("--- Testing Bernevig 2021 Abstract Citation ---")
    
    # 1. Initialize
    engine = PDFEngine()
    # PDF is now in tests/test_pdfs/
    pdf_path = os.path.join(os.path.dirname(__file__), "test_pdfs", "2021-bernevig-song-hotsc.pdf")
    engine.load_pdf(pdf_path)
    print(f"PDF Loaded. Pages: {engine.get_page_count()}")
    
    # 2. Get Context (Simulate App Logic)
    print("Fetching Context (Full Document)...")
    context_text = engine.get_context_text(page_count=None)
    print(f"Context Length: {len(context_text)} chars")
    
    # 3. Simulate Selection
    selection = "found in [1], and later in [3]"
    print(f"Simulating Selection: '{selection}'")
    
    # 4. Resolve via LLM
    print("Calling LLMController...")
    
    if not api_key:
        print("\n[INFO] No API Key found. Skipping actual LLM Call.")
        print(f"Captured Context ({len(context_text)} chars):")
        print(context_text[:500] + "...\n[Truncated]...\n" + context_text[-500:])
        return

    controller = LLMController(api_key=api_key)
    
    try:
        bibtex = controller.resolve_citation(selection, context_text)
        print("\n--- LLM Result ---")
        print(bibtex)
        print("------------------")
        
        # Validation checks
        if "@" in bibtex and "Song" in bibtex:
             print("SUCCESS: Found 'Song' (First Author of Ref 1) in BibTeX.")
        else:
             print("WARNING: Might not be the correct reference. Verify output.")
             
    except Exception as e:
        print(f"LLM Error: {e}")

if __name__ == "__main__":
    test_bernevig()
