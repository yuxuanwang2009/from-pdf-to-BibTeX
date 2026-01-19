import os
import re

# Try importing openai
try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

# Try importing google-generativeai
try:
    import google.generativeai as genai
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

class LLMHelper:
    AVAILABLE_MODELS = {
        "openai": ["gpt-4o", "gpt-5.2", "gpt-4-turbo"],
        "gemini": ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-1.0-pro"]
    }

    def __init__(self, api_key=None, provider="auto", model_name=None):
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.is_configured = bool(self.api_key)
        self.provider = provider
        self.client = None
        self.model_name = model_name
        
        if self.is_configured:
            # Auto-detect provider if default
            if self.provider == "auto":
                if self.api_key.startswith("sk-"):
                    self.provider = "openai"
                else:
                    self.provider = "gemini"

            if self.provider == "gemini" and HAS_GENAI:
                genai.configure(api_key=self.api_key)
                if not self.model_name:
                    self.model_name = "gemini-1.5-flash"
                self.model = genai.GenerativeModel(self.model_name)
            elif self.provider == "openai" and HAS_OPENAI:
                if not self.model_name:
                    self.model_name = "gpt-4o"
                self.client = OpenAI(api_key=self.api_key)

    def set_model(self, model_name):
        """Updates the active model."""
        self.model_name = model_name
        if self.provider == "gemini" and HAS_GENAI:
             self.model = genai.GenerativeModel(self.model_name)

    def _clean_llm_output(self, text):
        # Remove markdown code blocks
        text = re.sub(r'```(?:json|bibtex)?', '', text)
        text = re.sub(r'```', '', text)
        return text.strip()

    def validate_connection(self):
        """
        Tests if the current API Key is valid by making a minimal API call.
        Returns: (True, "Message") or (False, "Error Message")
        """
        if not self.is_configured:
            return False, "No API Key provided."

        try:
            if self.provider == "gemini" and HAS_GENAI:
                # Test by listing models (lightweight, no generation cost)
                # genai.list_models() returns a generator, so we wrap in list() to trigger the API call
                # explicitly. Limiting to 1 to avoid pagination delays.
                try:
                    next(genai.list_models())
                    return True, "Success: Gemini API Connected."
                except Exception as inner_e:
                    # If list_models fails, it usually raises permission error directly
                    raise inner_e

            elif self.provider == "openai" and self.client:
                # Test by listing models
                try:
                    self.client.models.list()
                    return True, "Success: OpenAI API Connected."
                except Exception as inner_e:
                    raise inner_e
            elif not HAS_OPENAI and self.provider == "openai":
                 return False, "Error: 'openai' library not installed."
            elif not HAS_GENAI and self.provider == "gemini":
                 return False, "Error: 'google.generativeai' library not installed."
            
            return False, f"Unknown provider or missing library for {self.provider}"

        except Exception as e:
            return False, f"Connection Failed: {str(e)}"

    def custom_query(self, prompt, json_mode=False, temperature=0):
        """
        Executes a raw prompt against the configured LLM.
        """
        if not self.is_configured:
            return None
        return self._query_llm(prompt, json_mode=json_mode, temperature=temperature)

    def _query_llm(self, prompt, json_mode=False, temperature=0):
        """Helper to handle provider differences"""
        try:
            if self.provider == "gemini" and HAS_GENAI:
                response = self.model.generate_content(
                    prompt,
                    generation_config={"temperature": temperature},
                )
                return self._clean_llm_output(response.text)
            elif self.provider == "openai" and self.client:
                kwargs = {
                    "model": self.model_name,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": temperature,
                }
                if json_mode:
                    kwargs["response_format"] = { "type": "json_object" }
                
                completion = self.client.chat.completions.create(**kwargs)
                return self._clean_llm_output(completion.choices[0].message.content)
        except Exception as e:
            print(f"LLM Query Error: {e}")
            raise e # Propagate error to caller (bib_app.py) for display
            
    def _clean_llm_output(self, text):
        # Remove markdown code blocks
        text = re.sub(r'```(?:json|bibtex)?', '', text)
        text = re.sub(r'```', '', text)
        return text.strip()
