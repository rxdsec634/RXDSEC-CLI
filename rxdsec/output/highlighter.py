"""
Advanced Code Highlighter for RxDsec CLI
=========================================
Syntax highlighting with language detection and customizable themes.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional, Dict

from rich.syntax import Syntax
from rich.text import Text

try:
    from pygments.lexers import get_lexer_by_name, get_lexer_for_filename, guess_lexer
    from pygments.util import ClassNotFound
    HAS_PYGMENTS = True
except ImportError:
    HAS_PYGMENTS = False

# Configure module logger
logger = logging.getLogger(__name__)

# Language aliases mapping
LANGUAGE_ALIASES: Dict[str, str] = {
    # Python
    'py': 'python',
    'python3': 'python',
    'py3': 'python',
    'pyw': 'python',
    
    # JavaScript/TypeScript
    'js': 'javascript',
    'mjs': 'javascript',
    'cjs': 'javascript',
    'ts': 'typescript',
    'tsx': 'tsx',
    'jsx': 'jsx',
    
    # Shell
    'sh': 'bash',
    'shell': 'bash',
    'zsh': 'bash',
    'fish': 'fish',
    'ps1': 'powershell',
    'bat': 'batch',
    'cmd': 'batch',
    
    # Web
    'htm': 'html',
    'xhtml': 'html',
    'vue': 'vue',
    'svelte': 'svelte',
    
    # Data formats
    'yml': 'yaml',
    'conf': 'ini',
    'cfg': 'ini',
    'toml': 'toml',
    
    # Systems
    'c++': 'cpp',
    'cxx': 'cpp',
    'h': 'c',
    'hpp': 'cpp',
    'hxx': 'cpp',
    'rs': 'rust',
    'go': 'go',
    'java': 'java',
    'kt': 'kotlin',
    'kts': 'kotlin',
    'scala': 'scala',
    'cs': 'csharp',
    'fs': 'fsharp',
    'vb': 'vbnet',
    'rb': 'ruby',
    'php': 'php',
    'swift': 'swift',
    'r': 'r',
    'R': 'r',
    
    # Query languages
    'sql': 'sql',
    'graphql': 'graphql',
    'gql': 'graphql',
    
    # Markup/Docs
    'md': 'markdown',
    'markdown': 'markdown',
    'rst': 'rst',
    'tex': 'latex',
    'latex': 'latex',
    
    # Config
    'dockerfile': 'dockerfile',
    'docker': 'dockerfile',
    'make': 'makefile',
    'makefile': 'makefile',
    'cmake': 'cmake',
    'nginx': 'nginx',
    
    # Other
    'diff': 'diff',
    'patch': 'diff',
    'json': 'json',
    'jsonc': 'json',
    'xml': 'xml',
    'svg': 'xml',
    'regex': 'regex',
    'asm': 'nasm',
    'assembly': 'nasm',
}

# Extension to language mapping
EXTENSION_LANGUAGES: Dict[str, str] = {
    '.py': 'python',
    '.pyw': 'python',
    '.pyi': 'python',
    '.js': 'javascript',
    '.mjs': 'javascript',
    '.cjs': 'javascript',
    '.ts': 'typescript',
    '.tsx': 'tsx',
    '.jsx': 'jsx',
    '.html': 'html',
    '.htm': 'html',
    '.css': 'css',
    '.scss': 'scss',
    '.sass': 'sass',
    '.less': 'less',
    '.json': 'json',
    '.yaml': 'yaml',
    '.yml': 'yaml',
    '.toml': 'toml',
    '.xml': 'xml',
    '.svg': 'xml',
    '.md': 'markdown',
    '.rst': 'rst',
    '.sh': 'bash',
    '.bash': 'bash',
    '.zsh': 'zsh',
    '.fish': 'fish',
    '.ps1': 'powershell',
    '.bat': 'batch',
    '.cmd': 'batch',
    '.c': 'c',
    '.h': 'c',
    '.cpp': 'cpp',
    '.cxx': 'cpp',
    '.cc': 'cpp',
    '.hpp': 'cpp',
    '.hxx': 'cpp',
    '.rs': 'rust',
    '.go': 'go',
    '.java': 'java',
    '.kt': 'kotlin',
    '.kts': 'kotlin',
    '.scala': 'scala',
    '.cs': 'csharp',
    '.fs': 'fsharp',
    '.vb': 'vbnet',
    '.rb': 'ruby',
    '.php': 'php',
    '.swift': 'swift',
    '.r': 'r',
    '.R': 'r',
    '.sql': 'sql',
    '.graphql': 'graphql',
    '.gql': 'graphql',
    '.dockerfile': 'dockerfile',
    '.lua': 'lua',
    '.perl': 'perl',
    '.pl': 'perl',
    '.pm': 'perl',
    '.ex': 'elixir',
    '.exs': 'elixir',
    '.erl': 'erlang',
    '.hrl': 'erlang',
    '.clj': 'clojure',
    '.cljs': 'clojure',
    '.hs': 'haskell',
    '.lhs': 'haskell',
    '.ml': 'ocaml',
    '.mli': 'ocaml',
    '.vim': 'vim',
    '.el': 'elisp',
    '.lisp': 'lisp',
    '.scm': 'scheme',
    '.rkt': 'racket',
    '.dart': 'dart',
    '.groovy': 'groovy',
    '.gradle': 'groovy',
}

# Default theme
DEFAULT_THEME = 'monokai'


def normalize_language(language: str) -> str:
    """
    Normalize a language identifier.
    
    Args:
        language: Raw language string
    
    Returns:
        Normalized language identifier
    """
    if not language:
        return 'text'
    
    language = language.lower().strip()
    
    # Check aliases
    if language in LANGUAGE_ALIASES:
        return LANGUAGE_ALIASES[language]
    
    return language


def get_language_from_fence(fence_line: str) -> str:
    """
    Extract language from a code fence line.
    
    Args:
        fence_line: Code fence line (e.g., "```python")
    
    Returns:
        Language identifier
    """
    match = re.match(r'^`{3,}(\w+)?', fence_line.strip())
    if match and match.group(1):
        return normalize_language(match.group(1))
    return 'text'


def detect_language(code: str, filename: Optional[str] = None) -> str:
    """
    Detect the programming language of code.
    
    Args:
        code: Source code
        filename: Optional filename for extension-based detection
    
    Returns:
        Detected language identifier
    """
    # Try filename first
    if filename:
        ext = Path(filename).suffix.lower()
        if ext in EXTENSION_LANGUAGES:
            return EXTENSION_LANGUAGES[ext]
        
        # Check if filename itself indicates language
        name = Path(filename).name.lower()
        if name == 'dockerfile':
            return 'dockerfile'
        elif name == 'makefile' or name == 'gnumakefile':
            return 'makefile'
        elif name in ('.bashrc', '.zshrc', '.bash_profile'):
            return 'bash'
    
    # Try pygments auto-detection
    if HAS_PYGMENTS:
        try:
            if filename:
                lexer = get_lexer_for_filename(filename, code)
                return lexer.aliases[0] if lexer.aliases else 'text'
        except ClassNotFound:
            pass
        
        try:
            lexer = guess_lexer(code)
            return lexer.aliases[0] if lexer.aliases else 'text'
        except ClassNotFound:
            pass
    
    # Heuristic detection based on content
    if code.strip().startswith('#!/'):
        shebang = code.split('\n')[0]
        if 'python' in shebang:
            return 'python'
        elif 'node' in shebang or 'deno' in shebang:
            return 'javascript'
        elif 'bash' in shebang or 'sh' in shebang:
            return 'bash'
        elif 'ruby' in shebang:
            return 'ruby'
        elif 'perl' in shebang:
            return 'perl'
    
    # Check for common patterns
    patterns = [
        (r'\bdef\s+\w+\s*\(', 'python'),
        (r'\bfunction\s+\w+\s*\(', 'javascript'),
        (r'\bconst\s+\w+\s*=', 'javascript'),
        (r'\blet\s+\w+\s*=', 'javascript'),
        (r'\bpub\s+fn\s+', 'rust'),
        (r'\bfn\s+\w+\s*\(', 'rust'),
        (r'\bfunc\s+\w+\s*\(', 'go'),
        (r'\bpackage\s+\w+', 'go'),
        (r'<\?php', 'php'),
        (r'\bpublic\s+class\s+', 'java'),
        (r'\bimport\s+java\.', 'java'),
        (r'\busing\s+System;', 'csharp'),
        (r'\bnamespace\s+\w+', 'csharp'),
        (r'^\s*#include\s*<', 'cpp'),
        (r'\bmodule\s+\w+\s+where', 'haskell'),
        (r'\bdefmodule\s+', 'elixir'),
        (r'<!DOCTYPE\s+html', 'html'),
        (r'<html', 'html'),
        (r'^---\s*$', 'yaml'),  # YAML front matter
        (r'^\s*\[\[', 'toml'),
        (r'^diff\s+--git', 'diff'),
    ]
    
    for pattern, lang in patterns:
        if re.search(pattern, code, re.MULTILINE | re.IGNORECASE):
            return lang
    
    return 'text'


def highlight_code(
    code: str, 
    language: Optional[str] = None,
    filename: Optional[str] = None,
    theme: str = DEFAULT_THEME,
    line_numbers: bool = False,
    start_line: int = 1,
    word_wrap: bool = True,
    background_color: Optional[str] = None
) -> Syntax:
    """
    Create a Rich Syntax object with syntax highlighting.
    
    Args:
        code: Source code to highlight
        language: Language identifier (auto-detected if not provided)
        filename: Optional filename for language detection
        theme: Pygments theme name
        line_numbers: Whether to show line numbers
        start_line: Starting line number
        word_wrap: Whether to wrap long lines
        background_color: Override background color
    
    Returns:
        Rich Syntax object for rendering
    """
    # Determine language
    if not language or language == 'text':
        if filename:
            language = detect_language(code, filename)
        else:
            language = detect_language(code)
    else:
        language = normalize_language(language)
    
    # Create Syntax object
    try:
        return Syntax(
            code,
            language,
            theme=theme,
            line_numbers=line_numbers,
            start_line=start_line,
            word_wrap=word_wrap,
            background_color=background_color
        )
    except Exception as e:
        logger.warning(f"Failed to highlight as {language}: {e}")
        # Fallback to plain text
        return Syntax(
            code,
            'text',
            theme=theme,
            line_numbers=line_numbers,
            word_wrap=word_wrap
        )


def highlight_inline(code: str, language: str = 'python') -> Text:
    """
    Create inline highlighted text (without panel).
    
    Args:
        code: Code snippet
        language: Language identifier
    
    Returns:
        Rich Text object with highlighting
    """
    # Simple inline highlighting using Text styles
    language = normalize_language(language)
    
    # Apply basic styling based on language patterns
    text = Text()
    
    # Very basic syntax highlighting for inline code
    if language in ('python', 'javascript', 'typescript'):
        # Highlight keywords
        keywords = {
            'python': ['def', 'class', 'import', 'from', 'return', 'if', 'else', 'for', 'while', 'try', 'except', 'with', 'as', 'in', 'not', 'and', 'or', 'True', 'False', 'None'],
            'javascript': ['function', 'const', 'let', 'var', 'return', 'if', 'else', 'for', 'while', 'try', 'catch', 'class', 'import', 'export', 'from', 'true', 'false', 'null', 'undefined'],
            'typescript': ['function', 'const', 'let', 'var', 'return', 'if', 'else', 'for', 'while', 'try', 'catch', 'class', 'import', 'export', 'from', 'true', 'false', 'null', 'undefined', 'interface', 'type'],
        }.get(language, [])
        
        pattern = r'\b(' + '|'.join(keywords) + r')\b'
        
        last_end = 0
        for match in re.finditer(pattern, code):
            # Add text before match
            if match.start() > last_end:
                text.append(code[last_end:match.start()])
            # Add highlighted keyword
            text.append(match.group(), style="bold magenta")
            last_end = match.end()
        
        # Add remaining text
        if last_end < len(code):
            text.append(code[last_end:])
    else:
        text.append(code)
    
    return text


__all__ = [
    'highlight_code',
    'highlight_inline',
    'detect_language',
    'normalize_language',
    'get_language_from_fence',
    'LANGUAGE_ALIASES',
    'EXTENSION_LANGUAGES',
    'DEFAULT_THEME',
]