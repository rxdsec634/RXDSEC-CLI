"""
RxDsec Output Package
======================
Production-ready output rendering and formatting system.
"""

from .renderer import (
    render_output,
    render_streaming,
    OutputParser,
    BlockRenderer,
    ContentBlock,
    BlockType,
)

from .narrator import (
    ToolNarrator,
    translate_tool_call,
    ToolCallInfo,
)

from .highlighter import (
    highlight_code,
    highlight_inline,
    detect_language,
    normalize_language,
    get_language_from_fence,
)

from .formats import (
    format_diff,
    format_plan,
    format_summary,
    format_table,
    format_code,
)

from .visual import (
    VisualFormatter,
    format_agent_output,
    ToolOutput,
    BULLET,
    TOOL_ARROW,
    NESTED_LINE,
)

__all__ = [
    # Main renderer
    'render_output',
    'render_streaming',
    'OutputParser',
    'BlockRenderer',
    'ContentBlock',
    'BlockType',
    
    # Narrator
    'ToolNarrator',
    'translate_tool_call',
    'ToolCallInfo',
    
    # Highlighter
    'highlight_code',
    'highlight_inline',
    'detect_language',
    'normalize_language',
    'get_language_from_fence',
    
    # Formatters
    'format_diff',
    'format_plan',
    'format_summary',
    'format_table',
    'format_code',
    
    # Visual formatter
    'VisualFormatter',
    'format_agent_output',
    'ToolOutput',
    'BULLET',
    'TOOL_ARROW',
    'NESTED_LINE',
]

__version__ = "1.0.0"