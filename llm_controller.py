import json
from llm_helper import LLMHelper

class LLMController:
    def __init__(self, api_key, provider="auto"):
        self.llm = LLMHelper(api_key=api_key, provider=provider)

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
