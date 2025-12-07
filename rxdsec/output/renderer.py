"""
Advanced Output Renderer for RxDsec CLI
========================================
Production-ready output transformation engine that converts raw LLM responses
into beautifully formatted terminal output with syntax highlighting, diff coloring,
and natural language narration.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Type, Union

from rich.console import Console, Group, RenderableType
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich.tree import Tree
from rich.rule import Rule
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.box import ROUNDED, DOUBLE, SIMPLE

from .narrator import translate_tool_call, ToolNarrator
from .highlighter import highlight_code, get_language_from_fence

# Configure module logger
logger = logging.getLogger(__name__)


class BlockType(Enum):
    """Types of content blocks in LLM output"""
    TEXT = auto()
    CODE = auto()
    DIFF = auto()
    TOOL = auto()
    PLAN = auto()
    SUMMARY = auto()
    TABLE = auto()
    HEADING = auto()
    LIST = auto()
    BLOCKQUOTE = auto()
    ERROR = auto()
    SUCCESS = auto()
    WARNING = auto()


@dataclass
class ContentBlock:
    """Represents a parsed content block"""
    type: BlockType
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __repr__(self):
        return f"ContentBlock({self.type.name}, {len(self.content)} chars)"


class OutputParser:
    """Parse raw LLM output into structured content blocks"""
    
    # Patterns for detecting content types
    PATTERNS = {
        'code_fence': re.compile(r'^```(\w*)\s*$', re.MULTILINE),
        'diff_header': re.compile(r'^diff --git|^---\s+\w|^\+\+\+\s+\w|^@@', re.MULTILINE),
        'tool_call': re.compile(r'^Tool:\s*(\w+)\s*\(', re.MULTILINE),
        'heading': re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE),
        'numbered_list': re.compile(r'^\s*(\d+)\.\s+', re.MULTILINE),
        'bullet_list': re.compile(r'^\s*[-*•]\s+', re.MULTILINE),
        'blockquote': re.compile(r'^>\s+', re.MULTILINE),
        'table_row': re.compile(r'^\|.+\|$', re.MULTILINE),
        'success_marker': re.compile(r'(✓|✅|success|completed?|done|passed)', re.IGNORECASE),
        'error_marker': re.compile(r'(✗|❌|error|failed?|exception)', re.IGNORECASE),
        'warning_marker': re.compile(r'(⚠|warning|caution|note)', re.IGNORECASE),
    }
    
    def parse(self, raw_text: str) -> List[ContentBlock]:
        """
        Parse raw text into content blocks.
        
        Args:
            raw_text: Raw LLM output text
        
        Returns:
            List of ContentBlock objects
        """
        blocks = []
        lines = raw_text.split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # Check for code fences
            code_match = self.PATTERNS['code_fence'].match(line)
            if code_match:
                language = code_match.group(1) or 'text'
                code_lines = []
                i += 1
                
                while i < len(lines) and not self.PATTERNS['code_fence'].match(lines[i]):
                    code_lines.append(lines[i])
                    i += 1
                
                i += 1  # Skip closing fence
                
                content = '\n'.join(code_lines)
                
                # Check if it's a diff
                if language == 'diff' or self.PATTERNS['diff_header'].search(content):
                    blocks.append(ContentBlock(
                        type=BlockType.DIFF,
                        content=content,
                        metadata={'language': 'diff'}
                    ))
                else:
                    blocks.append(ContentBlock(
                        type=BlockType.CODE,
                        content=content,
                        metadata={'language': language}
                    ))
                continue
            
            # Check for diff without code fence
            if line.startswith('diff --git') or (line.startswith('---') and i + 1 < len(lines) and lines[i + 1].startswith('+++')):
                diff_lines = [line]
                i += 1
                
                while i < len(lines) and not (lines[i].strip() == '' and i + 1 < len(lines) and not lines[i + 1].startswith((' ', '+', '-', '@', 'diff'))):
                    diff_lines.append(lines[i])
                    i += 1
                
                blocks.append(ContentBlock(
                    type=BlockType.DIFF,
                    content='\n'.join(diff_lines),
                    metadata={'language': 'diff'}
                ))
                continue
            
            # Check for tool calls
            tool_match = self.PATTERNS['tool_call'].match(line)
            if tool_match:
                blocks.append(ContentBlock(
                    type=BlockType.TOOL,
                    content=line,
                    metadata={'tool_name': tool_match.group(1)}
                ))
                i += 1
                continue
            
            # Check for headings
            heading_match = self.PATTERNS['heading'].match(line)
            if heading_match:
                level = len(heading_match.group(1))
                text = heading_match.group(2)
                blocks.append(ContentBlock(
                    type=BlockType.HEADING,
                    content=text,
                    metadata={'level': level}
                ))
                i += 1
                continue
            
            # Check for numbered lists (potential plans)
            if self.PATTERNS['numbered_list'].match(line):
                list_lines = [line]
                i += 1
                
                while i < len(lines) and (self.PATTERNS['numbered_list'].match(lines[i]) or (lines[i].startswith('   ') and lines[i].strip())):
                    list_lines.append(lines[i])
                    i += 1
                
                # Check if it looks like a plan
                is_plan = any(kw in '\n'.join(list_lines).lower() for kw in ['step', 'plan', 'task', 'action', 'phase'])
                
                blocks.append(ContentBlock(
                    type=BlockType.PLAN if is_plan else BlockType.LIST,
                    content='\n'.join(list_lines),
                    metadata={'list_type': 'numbered'}
                ))
                continue
            
            # Check for bullet lists
            if self.PATTERNS['bullet_list'].match(line):
                list_lines = [line]
                i += 1
                
                while i < len(lines) and (self.PATTERNS['bullet_list'].match(lines[i]) or (lines[i].startswith('  ') and lines[i].strip())):
                    list_lines.append(lines[i])
                    i += 1
                
                blocks.append(ContentBlock(
                    type=BlockType.LIST,
                    content='\n'.join(list_lines),
                    metadata={'list_type': 'bullet'}
                ))
                continue
            
            # Check for tables
            if self.PATTERNS['table_row'].match(line):
                table_lines = [line]
                i += 1
                
                while i < len(lines) and (self.PATTERNS['table_row'].match(lines[i]) or lines[i].strip().startswith('|')):
                    table_lines.append(lines[i])
                    i += 1
                
                blocks.append(ContentBlock(
                    type=BlockType.TABLE,
                    content='\n'.join(table_lines),
                    metadata={}
                ))
                continue
            
            # Regular text - collect until we hit something else
            text_lines = [line]
            i += 1
            
            while i < len(lines):
                next_line = lines[i]
                
                # Stop if we hit a special block
                if any([
                    self.PATTERNS['code_fence'].match(next_line),
                    self.PATTERNS['diff_header'].match(next_line),
                    self.PATTERNS['tool_call'].match(next_line),
                    self.PATTERNS['heading'].match(next_line),
                    self.PATTERNS['table_row'].match(next_line),
                    next_line.startswith('diff --git'),
                ]):
                    break
                
                text_lines.append(next_line)
                i += 1
            
            text_content = '\n'.join(text_lines).strip()
            
            if text_content:
                # Determine text type
                block_type = BlockType.TEXT
                
                if self.PATTERNS['success_marker'].search(text_content):
                    block_type = BlockType.SUCCESS
                elif self.PATTERNS['error_marker'].search(text_content):
                    block_type = BlockType.ERROR
                elif self.PATTERNS['warning_marker'].search(text_content):
                    block_type = BlockType.WARNING
                
                blocks.append(ContentBlock(
                    type=block_type,
                    content=text_content,
                    metadata={}
                ))
        
        return blocks


class BlockRenderer:
    """Render content blocks to Rich renderables"""
    
    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()
        self.narrator = ToolNarrator()
    
    def render(self, block: ContentBlock) -> RenderableType:
        """Render a content block to Rich renderable"""
        renderer_method = getattr(self, f'_render_{block.type.name.lower()}', self._render_text)
        return renderer_method(block)
    
    def _render_text(self, block: ContentBlock) -> RenderableType:
        """Render plain text"""
        return Text(block.content)
    
    def _render_code(self, block: ContentBlock) -> RenderableType:
        """Render code with syntax highlighting"""
        language = block.metadata.get('language', 'text')
        return Panel(
            highlight_code(block.content, language),
            title=f"Code ({language})" if language != 'text' else "Code",
            border_style="cyan",
            box=ROUNDED
        )
    
    def _render_diff(self, block: ContentBlock) -> RenderableType:
        """Render diff with coloring"""
        from .formats.diff import format_diff
        return format_diff(block.content)
    
    def _render_tool(self, block: ContentBlock) -> RenderableType:
        """Render tool call with natural language narration"""
        narration = self.narrator.translate(block.content)
        return Text(f"🔧 {narration}", style="dim cyan")
    
    def _render_plan(self, block: ContentBlock) -> RenderableType:
        """Render a plan with checkmarks"""
        from .formats.plan import format_plan
        return format_plan(block.content)
    
    def _render_list(self, block: ContentBlock) -> RenderableType:
        """Render a list"""
        lines = block.content.split('\n')
        text = Text()
        
        for line in lines:
            if line.strip():
                # Replace bullet points with styled versions
                line = re.sub(r'^(\s*)[-*]\s+', r'\1• ', line)
                text.append(line + '\n')
        
        return text
    
    def _render_heading(self, block: ContentBlock) -> RenderableType:
        """Render a heading"""
        level = block.metadata.get('level', 1)
        styles = {
            1: ("bold magenta", "═"),
            2: ("bold cyan", "─"),
            3: ("bold blue", "·"),
            4: ("bold", ""),
            5: ("dim bold", ""),
            6: ("dim", "")
        }
        
        style, char = styles.get(level, ("", ""))
        
        if char:
            return Rule(block.content, style=style, characters=char)
        else:
            return Text(block.content, style=style)
    
    def _render_table(self, block: ContentBlock) -> RenderableType:
        """Render a markdown table"""
        from .formats.table import format_table
        return format_table(block.content)
    
    def _render_summary(self, block: ContentBlock) -> RenderableType:
        """Render a summary block"""
        from .formats.summary import format_summary
        return format_summary(block.content)
    
    def _render_success(self, block: ContentBlock) -> RenderableType:
        """Render success message"""
        return Panel(
            Text(block.content, style="green"),
            title="✅ Success",
            border_style="green",
            box=ROUNDED
        )
    
    def _render_error(self, block: ContentBlock) -> RenderableType:
        """Render error message"""
        return Panel(
            Text(block.content, style="red"),
            title="❌ Error",
            border_style="red",
            box=ROUNDED
        )
    
    def _render_warning(self, block: ContentBlock) -> RenderableType:
        """Render warning message"""
        return Panel(
            Text(block.content, style="yellow"),
            title="⚠️ Warning",
            border_style="yellow",
            box=ROUNDED
        )
    
    def _render_blockquote(self, block: ContentBlock) -> RenderableType:
        """Render blockquote"""
        content = re.sub(r'^>\s*', '', block.content, flags=re.MULTILINE)
        return Panel(
            Text(content, style="italic dim"),
            border_style="dim",
            box=SIMPLE
        )


def render_output(raw_text: str, console: Optional[Console] = None) -> RenderableType:
    """
    Render raw LLM output into formatted Rich output.
    
    This is the main entry point for output rendering. It:
    1. Parses raw text into content blocks
    2. Renders each block with appropriate formatting
    3. Returns grouped content (no panel wrapper)
    
    Args:
        raw_text: Raw text from LLM
        console: Optional Rich console for rendering
    
    Returns:
        Rich renderable object
    """
    console = console or Console()
    parser = OutputParser()
    renderer = BlockRenderer(console)
    
    # Parse into blocks
    blocks = parser.parse(raw_text)
    
    if not blocks:
        return Text(raw_text)
    
    # Render each block
    renderables = []
    
    for block in blocks:
        try:
            rendered = renderer.render(block)
            renderables.append(rendered)
        except Exception as e:
            logger.warning(f"Error rendering block {block.type}: {e}")
            renderables.append(Text(block.content))
    
    # Group all renderables - no panel wrapping
    if len(renderables) == 1:
        return renderables[0]
    else:
        return Group(*renderables)


def render_streaming(
    text_iterator,
    console: Optional[Console] = None,
    title: str = "RxDsec Agent"
) -> str:
    """
    Render streaming output in real-time.
    
    Args:
        text_iterator: Iterator yielding text chunks
        console: Rich console
        title: Panel title
    
    Returns:
        Complete accumulated text
    """
    console = console or Console()
    accumulated = []
    
    with console.status("[bold blue]Thinking...[/bold blue]", spinner="dots") as status:
        for chunk in text_iterator:
            accumulated.append(chunk)
            # Could update display here for truly streaming output
    
    full_text = ''.join(accumulated)
    rendered = render_output(full_text, console)
    console.print(rendered)
    
    return full_text


# Re-export for backward compatibility
__all__ = [
    'render_output',
    'render_streaming',
    'OutputParser',
    'BlockRenderer',
    'ContentBlock',
    'BlockType',
]