"""
Output Format Modules for RxDsec CLI
=====================================
Specialized formatters for different content types.
"""

from .diff import format_diff, format_inline_diff, summarize_diff
from .plan import format_plan, format_checklist, parse_plan_items
from .summary import format_summary, format_stats_summary, format_completion_summary
from .table import format_table, format_key_value_table, format_comparison_table
from .code import format_code, format_code_snippet

__all__ = [
    # Diff formatting
    'format_diff',
    'format_inline_diff', 
    'summarize_diff',
    
    # Plan formatting
    'format_plan',
    'format_checklist',
    'parse_plan_items',
    
    # Summary formatting
    'format_summary',
    'format_stats_summary',
    'format_completion_summary',
    
    # Table formatting
    'format_table',
    'format_key_value_table',
    'format_comparison_table',
    
    # Code formatting
    'format_code',
    'format_code_snippet',
]
