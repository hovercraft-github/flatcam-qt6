# appParsers/PdfStreamParser.py
"""
PDF Stream Parser Module

Provides pluggable PDF content stream extraction with multiple backends:
- PurePythonPdfParser: Uses only standard library (zlib + re, default)
- PikePdfParser: Uses pikepdf library (optional, lazy import when enabled)

Configuration (via defaults.py):
    pdf_python_parser: True   -> Use pure-python parser (default, recommended)
    pdf_python_parser: False  -> Use pikepdf parser (requires pikepdf installation)

Usage:
    from appParsers.PdfStreamParser import get_pdf_parser
    
    # Get parser based on defaults.py configuration
    parser = get_pdf_parser(app.defaults)
    content = parser.extract_content_streams("file.pdf")
    
    # Or use convenience function
    from appParsers.PdfStreamParser import parse_pdf_content_streams
    content = parse_pdf_content_streams("file.pdf", app.defaults)

Why pure-python is default:
    - No external dependencies
    - Works with all Python 3.11+ installations
    - Latest pikepdf versions crash on import even with try/except
    - Lazy import of pikepdf only when explicitly enabled
    
Note: Only the first page of PDFs is extracted (existing FlatCAM behavior).
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import logging
import re
import zlib

log = logging.getLogger('base')


class PdfStreamParserBase(ABC):
    """
    Abstract base class for PDF content stream parsers.
    
    Extracts and decompresses PDF content streams into text format
    that can be parsed by ParsePDF.py
    """
    
    @abstractmethod
    def extract_content_streams(self, filename: str) -> str:
        """
        Extract and decompress content streams from a PDF file.
        
        Only extracts from the first page (existing FlatCAM behavior).
        
        Args:
            filename: Path to the PDF file
            
        Returns:
            Decompressed content stream text (PDF operators as text)
            
        Raises:
            PdfParserError: If parsing fails
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if this parser backend is available (dependencies installed).
        
        Returns:
            True if parser can be used, False otherwise
        """
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Return human-readable parser name."""
        pass


class PdfParserError(Exception):
    """Exception raised when PDF parsing fails."""
    pass


class PurePythonPdfParser(PdfStreamParserBase):
    """
    PDF parser using only Python standard library.
    
    Uses zlib for decompression and regex for stream extraction.
    Supports FlateDecode compression (most common).
    
    This is the DEFAULT parser - no external dependencies required.
    
    Limitations:
    - Does not support encrypted PDFs
    - Does not support LZW or other compression filters
    - Does not support object streams
    - May fail on complex PDF structures
    """
    
    # Regex to find PDF streams
    # Pattern: <<dictionary>> stream <compressed_data> endstream
    STREAM_PATTERN = re.compile(
        rb'<<.*?>>\s*stream\s*\r?\n(.*?)\s*\r?\n?\s*endstream',
        re.DOTALL
    )
    
    # Pattern to check for FlateDecode filter
    FLATE_DECODE_PATTERN = re.compile(rb'/FlateDecode')
    
    # Pattern to find BDC/EMC layer markers (PDF 1.2+)
    LAYER_PATTERN = re.compile(rb'BDC(.*?)EMC', re.DOTALL)
    
    @property
    def name(self) -> str:
        return "pure-python"
    
    def is_available(self) -> bool:
        # Always available - uses only standard library
        return True
    
    def extract_content_streams(self, filename: str) -> str:
        """
        Extract content streams using pure Python (zlib + regex).
        
        Only extracts from the first page (existing FlatCAM behavior).
        
        BDC/EMC layer markers (PDF 1.2+) are NOT searched for in raw PDF binary -
        they appear INSIDE compressed content streams and won't be found as raw bytes.
        The correct approach (matching pdf2gerb.pl) is to first decompress all streams,
        then search for markers in decompressed text if needed. Since _extract_all_streams()
        already correctly extracts and decompresses the content, we use it directly.
        
        Args:
            filename: Path to PDF file
            
        Returns:
            Decompressed content stream text
            
        Raises:
            PdfParserError: If parsing fails
        """
        try:
            with open(filename, "rb") as f:
                pdf_data = f.read()
            
            # Extract and decompress all FlateDecode streams
            # This is the correct approach - BDC/EMC markers are inside compressed
            # content streams, so we must decompress first before searching for them
            result = self._extract_all_streams(pdf_data)
            
            if not result.strip():
                raise PdfParserError("No valid content streams found")
            
            return result
            
        except PdfParserError:
            raise
        except Exception as e:
            raise PdfParserError(f"pure-python parsing failed: {str(e)}")
    
    def _extract_all_streams(self, pdf_data: bytes) -> str:
        """
        Extract and decompress all FlateDecode streams.
        
        Args:
            pdf_data: Raw PDF file data
            
        Returns:
            Concatenated decompressed stream content
        """
        output_parts = []
        
        for match in self.STREAM_PATTERN.finditer(pdf_data):
            stream_dict = pdf_data[match.start():match.start() + match.group(0).find(b'stream')]
            compressed_data = match.group(1)
            
            # Only process FlateDecode streams
            if not self.FLATE_DECODE_PATTERN.search(stream_dict):
                continue
            
            try:
                decompressed = self._decompress_stream(compressed_data)
                if decompressed:
                    try:
                        text = decompressed.decode('utf-8', errors='replace')
                    except Exception:
                        text = decompressed.decode('latin-1', errors='replace')
                    output_parts.append(text)
            except Exception as e:
                log.debug(f"Stream decompression failed: {e}")
                continue
        
        return '\n'.join(output_parts)
    
    def _decompress_if_needed(self, data: bytes) -> Optional[bytes]:
        """Try to decompress data if it's compressed."""
        # Try direct decode first
        try:
            data.decode('utf-8')
            return data  # Already decompressed
        except UnicodeDecodeError:
            pass
        
        # Try decompression
        return self._decompress_stream(data)
    
    def _decompress_stream(self, compressed_data: bytes) -> Optional[bytes]:
        """
        Decompress FlateDecode stream using zlib.
        
        Args:
            compressed_data: Raw compressed stream data
            
        Returns:
            Decompressed data or None if decompression fails
        """
        # Try different zlib decompression strategies
        # -15 = raw deflate (no zlib header) - most common for PDFs
        try:
            return zlib.decompress(compressed_data, -15)
        except zlib.error:
            pass
        
        # Try with standard zlib header
        try:
            return zlib.decompress(compressed_data)
        except zlib.error:
            pass
        
        # Try with auto-detect header (15 + 32)
        try:
            return zlib.decompress(compressed_data, 15 + 32)
        except zlib.error:
            pass
        
        # All strategies failed - data might be corrupted or use different filter
        log.debug("All zlib decompression strategies failed")
        return None


class PikePdfParser(PdfStreamParserBase):
    """
    PDF parser using pikepdf library.
    
    Provides full PDF support including:
    - Multiple compression filters
    - Object streams
    - Encrypted PDFs (with password)
    - Complex PDF structures
    
    IMPORTANT: pikepdf is imported LAZY (only when this class is instantiated).
    This avoids import crashes on systems with incompatible pikepdf versions.
    
    Note: Only extracts content from the first page (existing FlatCAM behavior).
    """
    
    def __init__(self):
        """
        Lazy import of pikepdf - only import when actually creating instance.
        
        This prevents import-time crashes from breaking the application.
        """
        self._pikepdf = None
        self._available = None
        self._try_import()
    
    def _try_import(self) -> None:
        """
        Attempt lazy import of pikepdf.
        
        Sets self._available to True if import succeeds, False otherwise.
        """
        if self._available is not None:
            return  # Already tried
        
        try:
            # LAZY IMPORT - only happens when PikePdfParser is instantiated
            import pikepdf
            from pikepdf import Pdf, parse_content_stream
            self._pikepdf = {
                'Pdf': Pdf,
                'parse_content_stream': parse_content_stream,
            }
            self._available = True
            log.debug("pikepdf imported successfully (lazy import)")
        except Exception as e:
            log.warning(f"pikepdf lazy import failed: {e}")
            self._pikepdf = None
            self._available = False
    
    @property
    def name(self) -> str:
        return "pikepdf"
    
    def is_available(self) -> bool:
        """Check if pikepdf was successfully imported."""
        return self._available is True
    
    def extract_content_streams(self, filename: str) -> str:
        """
        Extract content streams using pikepdf.
        
        Only extracts from the first page (existing FlatCAM behavior).
        
        Args:
            filename: Path to PDF file
            
        Returns:
            Decompressed content stream text
            
        Raises:
            PdfParserError: If pikepdf is not available or parsing fails
        """
        if not self.is_available():
            raise PdfParserError(
                "pikepdf is not available. "
                "Install with: pip install pikepdf>=2.0, "
                "or set pdf_python_parser=True in defaults.py to use pure-python parser"
            )
        
        try:
            Pdf = self._pikepdf['Pdf']
            parse_content_stream = self._pikepdf['parse_content_stream']
            
            with open(filename, "rb") as f:
                pdf = Pdf.open(f)
                
                # Extract FIRST PAGE ONLY (existing FlatCAM behavior)
                page = pdf.pages[0]
                decomp_file = ''
                
                for operands, command in parse_content_stream(page):
                    line = ''
                    for op in operands:
                        try:
                            line += str(op) + ' '
                        except Exception:
                            # Skip operands that can't be converted to string
                            pass
                    line += str(command)
                    decomp_file += line + '\n'
                
                if not decomp_file.strip():
                    raise PdfParserError("Empty content stream or parsing error")
                
                return decomp_file
                
        except Exception as e:
            raise PdfParserError(f"pikepdf parsing failed: {str(e)}")


def get_pdf_parser(app_defaults: Optional[Dict[str, Any]] = None) -> PdfStreamParserBase:
    """
    Factory function to get PDF parser based on configuration.
    
    Args:
        app_defaults: Application defaults dict (from defaults.py).
                     If None, uses pure-python parser as safe default.
    
    Returns:
        PdfStreamParserBase instance
        
    Raises:
        PdfParserError: If selected parser is not available
    """
    # Default to pure-python (safe, no dependencies)
    use_pure_python = True
    
    if app_defaults is not None:
        # Check configuration: pdf_python_parser=True means use pure-python
        use_pure_python = app_defaults.get('pdf_python_parser', True)
    
    if use_pure_python:
        log.debug("Using pure-python PDF parser (pdf_python_parser=True)")
        return PurePythonPdfParser()
    else:
        # User explicitly requested pikepdf
        log.debug("Using pikepdf PDF parser (pdf_python_parser=False)")
        parser = PikePdfParser()
        
        if not parser.is_available():
            log.warning(
                "pikepdf parser requested but not available. "
                "Falling back to pure-python parser. "
                "Set pdf_python_parser=True in defaults.py to suppress this warning."
            )
            return PurePythonPdfParser()
        
        return parser


def get_pdf_parser_by_name(name: str) -> PdfStreamParserBase:
    """
    Factory function to get PDF parser by explicit name.
    
    Args:
        name: Parser name ('pure-python' or 'pikepdf')
    
    Returns:
        PdfStreamParserBase instance
    """
    if name == 'pure-python':
        return PurePythonPdfParser()
    elif name == 'pikepdf':
        return PikePdfParser()
    else:
        raise PdfParserError(f"Unknown parser name: {name}")


def parse_pdf_content_streams(
    filename: str,
    app_defaults: Optional[Dict[str, Any]] = None
) -> str:
    """
    Extract content streams from a PDF file.
    
    Only extracts from the first page (existing FlatCAM behavior).
    
    Args:
        filename: Path to PDF file
        app_defaults: Application defaults dict
        
    Returns:
        Decompressed content stream text
        
    Raises:
        PdfParserError: If parsing fails
    """
    parser = get_pdf_parser(app_defaults)
    return parser.extract_content_streams(filename)


# Exports
__all__ = [
    'PdfStreamParserBase',
    'PdfParserError',
    'PurePythonPdfParser',
    'PikePdfParser',
    'get_pdf_parser',
    'get_pdf_parser_by_name',
    'parse_pdf_content_streams',
]
