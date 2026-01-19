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
        The full PDF text is provided with page markers (e.g., --- Page N ---).

        TASK:
        Identify the START and END page numbers of the bibliography/references section.

        CRITICAL INSTRUCTIONS:
        1.  **LOCATE THE SECTION**: Look for a section heading like "References", "Bibliography", or "Literature Cited".
            -   **IGNORE** the Table of Contents (ToC). A ToC line like "References ...... 42" is NOT the section.
            -   **IGNORE** internal text references like "see References section".

        2.  **VERIFY CONTENT**: The pages MUST contain a list of citations.
            -   Look for citation patterns like: `[1]`, `[2]`, `1.`, `2.`, `Smith, J. (2020)`.
            -   If a page has the header "References" but contains only "...... 12" or similar dots/page numbers, it is a ToC page. DO NOT select it.

        3.  **DETERMINE RANGE**:
            -   **start_page**: The page where the bibliography heading appears.
            -   **end_page**: The last page containing citation entries.
            -   Note: The bibliography might end *before* Appendices or continue to the very end of the document.

        OUTPUT (JSON ONLY):
        {{
          "start_page": 12,
          "end_page": 18,
          "reason": "Found 'References' heading followed by [1]..[20] citations."
        }}
        
        If NOT found, return null for values.

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

    def detect_citation_style(self, first_pages_text):
        """
        Analyzes the first few pages (text) to identify the citation style used in the MAIN BODY.
        """
        prompt = f"""
        You are an expert at analyzing academic documents.
        
        TASK:
        1. Read the input text (which covers the first few pages of a PDF).
        2. Locate the start of the MAIN BODY TEXT (Introduction or first chapter).
           - IGNORE the Abstract, Table of Contents, Title, and Authors list.
        3. Identify the citation style used *within that main body text*.
        
        INPUT TEXT:
        \"\"\"{first_pages_text}\"\"\"
        
        INSTRUCTIONS:
        - Determine the specific style. Common styles:
           - "Numeric Brackets": [1], [2-5]
           - "Author-Year": (Smith 2020), (Jones et al., 2021)
           - "Superscript": Word^1 or Word1
           - "Alpha-Numeric": [Smi20]
        - If the document uses footnotes for citations, return "Footnotes".
        - If no clear citations are found in the main text, return "Unknown/Generic".
        
        OUTPUT:
        Return ONLY a short description string of the style. Do not explain.
        Example: "Numeric Brackets"
        """
        return self.llm.custom_query(prompt).strip()

    def resolve_citation(self, selection_text, context_text, style_hint=None):
        """
        Analyzes the user's selection and the document context to return a BibTeX entry.
        """
        style_instruction = ""
        if style_hint and "Unknown" not in style_hint:
             style_instruction = f"NOTE: The document uses '{style_hint}' citation style. STRICTLY enforce this style when identifying handles."

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
           {style_instruction}
           - Identify ONLY explicit citation handles. Valid formats include:
             - Numeric: "[1]", "[1-3]", "[1, 5]".
             - Author-Year: "(Smith 2020)", "(Doe, 2021)", "(Jones et al. 2022)", "(Wang et al., 2024a)".
             - Organization-Year: "(Art of Problem Solving, 2025)", "(OpenAI 2023)".
             - Multiple Author-Year: "(Doe 2020; Lee 2021)", "(Smith, 2010; Jones, 2012)".
             - Textual: "Ref. 12", "Reference 3", "Refs. 4-5".
           - IGNORE numbers that are part of the text, such as "Fig. 2", "2D", "equation (5)", "Section 3".
           - IF the selection does NOT contain any clear citation handle:
             - Return exactly: "% No valid citation handles found in selection."
             - DO NOT hallucinate a reference just because the text discusses a topic.
             - DO NOT guess.
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
           - If no valid citation handles are found, return exactly: "% No valid citation handles found in selection."
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
