import json
import re
from llm_helper import LLMHelper

class LLMController:
    def __init__(self, api_key, provider="auto"):
        self.llm = LLMHelper(api_key=api_key, provider=provider)

    def resolve_bibliography_range(self, full_text):
        """
        Uses the LLM to identify the bibliography page range from full PDF text.
        Returns a dict with start_page/end_page (1-based) or None if not found.
        """
        prompt = f"""
        You are an expert at identifying bibliography/reference sections in PDFs.

        INPUT:
        The full PDF text is provided with page markers like:
        --- Page 1 ---
        ...content...
        --- Page 2 ---
        ...content...

        TASK:
        Find the page range that contains the bibliography/references section.

        RULES:
        - Only use the provided text and page markers.
        - Return 1-based page numbers inclusive.
        - If the bibliography is not found, return nulls.

        OUTPUT (JSON ONLY):
        {{
          "start_page": 12,
          "end_page": 18,
          "reason": "Found 'References' heading and numbered entries."
        }}

        FULL TEXT:
        \"\"\"{full_text}\"\"\"
        """

        raw = self.llm.custom_query(prompt, json_mode=True, temperature=0)
        if not raw:
            return None
        try:
            data = json.loads(raw)
            start_page = data.get("start_page")
            end_page = data.get("end_page")
            if isinstance(start_page, int) and isinstance(end_page, int):
                return {
                    "start_page": start_page,
                    "end_page": end_page,
                    "reason": data.get("reason", ""),
                }
        except Exception:
            start_match = re.search(r'"?start_page"?\s*[:=]\s*(\d+)', raw)
            end_match = re.search(r'"?end_page"?\s*[:=]\s*(\d+)', raw)
            if start_match and end_match:
                return {
                    "start_page": int(start_match.group(1)),
                    "end_page": int(end_match.group(1)),
                    "reason": "",
                }
            range_match = re.search(r'(\d+)\s*[-–—]\s*(\d+)', raw)
            if range_match:
                return {
                    "start_page": int(range_match.group(1)),
                    "end_page": int(range_match.group(2)),
                    "reason": "",
                }
        return None

    def resolve_citation(self, selection_text, context_text):
        """
        Analyzes the user's selection and the document context to return a BibTeX entry.
        """
        prompt = f"""
        You are an expert Research Assistant and BibTeX Resolver.
        
        TASK:
        The user has selected a snippet of text from a PDF. 
        Your goal is to generate a correct, complete BibTeX entry for the citation represented by that selection.

        INPUTS:
        1. User Selection: "{selection_text}"
        2. document_context (Bibliography Section text): 
        \"\"\"{context_text}\"\"\"

        INSTRUCTIONS:
        1. ANALYZE the Selection:
           - Identify EVERY SINGLE citation handle in the text, even if they are far apart (e.g. "...[1]... and also [5]").
           - EXPAND ranges: "[1-3]" -> 1, 2, 3.
           - Range separators may include "-", "–", "—", "‑", "−", "﹣", "－". Treat them as equivalent.
           - IF the selection is a bibliography list, parse all lines.
        
        2. LOCATE in Context:
           - For EACH identified handle/key, search the `document_context` to find the full reference text.
           - E.g. If input is "[1-2]", look for "1. ..." and "2. ..." in the context.
        
        3. EXTRACT & CONVERT:
           - Convert EVERY identified reference into a valid BibTeX entry.
           - Ensure correct Authors, Title, Journal, Volume, Page, DOI.
           - If metadata is missing, do not hallucinate.
        
        4. OUTPUT:
           - Return a block of BibTeX entries, separated by newlines.
           - Return ONLY the BibTeX. No markdown, no conversation.
           - Error messages, if any, need to be commented out using "%".
        """
        
        # We use the existing query method from LLMHelper
        # assuming LLMHelper has a generic 'query' or we use parse_bibtex's logic
        # Actually, LLMHelper mainly has specific methods.
        # Let's use a direct call pattern or add a generic query method to LLMHelper.
        # For now, we'll access the internal _query_llm or similar if available, 
        # OR we just instantiate a tailored method here.
        
        # Since LLMHelper isn't fully generic in the current codebase (it has parse_bibtex, etc),
        # We will assume we can use `llm.parse_bibtex` BUT that method uses a specific prompt.
        # We need a custom prompt.
        # I will use `llm._query_llm` if I made it public, but I didn't yet.
        # Let's use `llm.parse_bibtex` but PASS the prompt as the "raw_text" is a hack.
        # Better: Update LLMHelper to support generic queries.
        
        # Reuse the helper's connection logic, but we might need to extend LLMHelper.
        # For this file, I'll rely on a new method I'll add to LLMHelper: `custom_query(prompt)`
        
        return self.llm.custom_query(prompt)
