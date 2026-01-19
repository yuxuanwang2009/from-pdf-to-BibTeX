import fitz  # PyMuPDF
from typing import List, Tuple

class PDFEngine:
    def __init__(self):
        self.doc = None
        self.path = None

    def load_pdf(self, path: str):
        self.path = path
        if self.doc:
            self.doc.close()
        self.doc = fitz.open(path)

    def get_page_count(self):
        if self.doc:
            return len(self.doc)
        return 0

    def get_page_pixmap(self, page_num: int, zoom: float = 1.0):
        if not self.doc:
            return None
        page = self.doc.load_page(page_num)
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        return pix

    def get_text_in_rect(self, page_num: int, rect: fitz.Rect) -> str:
        if not self.doc:
            return ""
        page = self.doc[page_num]
        return page.get_text("text", clip=rect)

    def get_context_text(self, page_count=None) -> str:
        """
        Returns the text of the PDF to serve as bibliography context.
        Defaults to FULL DOCUMENT to ensure all references are visible.
        For extremely large documents (>100 pages), might want to smart-limit,
        but for standard papers (30-50 pages), full text is best for the LLM.
        """
        if not self.doc: 
            return ""
        
        full_text = ""
        total_pages = len(self.doc)
        
        # Heuristic: If requested page_count is None, try to get everything.
        # But if document is huge (> 100 pages), fallback to First 10 + Last 20.
        if page_count is None:
            if total_pages > 100:
                print(f"[PDF Engine] Large document ({total_pages} pages). Using tailored context.")
                # First 5 pages (Intro) + Last 30 pages (Refs)
                pages_to_read = list(range(0, 5)) + list(range(max(5, total_pages - 30), total_pages))
            else:
               pages_to_read = range(total_pages)
        else:
            # Legacy "Last N" mode if specifically requested
            start_page = max(0, total_pages - page_count)
            pages_to_read = range(start_page, total_pages)
            
        for i in pages_to_read:
            # Header marker for LLM context
            full_text += f"\n--- Page {i+1} ---\n"
            full_text += self.doc[i].get_text()
            
        return full_text

    def find_citations_on_page(self, page_num: int) -> List[Tuple[fitz.Rect, str]]:
        """
        Legacy method required by GUI (render_page).
        Returns empty list as we no longer pre-calculate citation boxes.
        """
        return []
        
    def get_bib_entry(self, key: str) -> str:
        # Legacy placeholder
        return ""
