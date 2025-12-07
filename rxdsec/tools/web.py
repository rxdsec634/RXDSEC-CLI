"""
Advanced Web Fetch Tool for RxDsec CLI
=======================================
Production-ready HTTP client with rate limiting, domain whitelisting,
content extraction, and comprehensive error handling.
"""

from __future__ import annotations

import hashlib
import html
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

try:
    import requests
    from requests.adapters import HTTPAdapter
    from requests.packages.urllib3.util.retry import Retry
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from .base import tool, ToolResult, ToolStatus

# Configure module logger
logger = logging.getLogger(__name__)

# Default timeout for requests
DEFAULT_TIMEOUT = 15

# Maximum response size (5MB)
MAX_RESPONSE_SIZE = 5 * 1024 * 1024

# Maximum content length to return (50KB)
MAX_CONTENT_LENGTH = 50 * 1024

# Rate limiting: minimum seconds between requests to same domain
RATE_LIMIT_SECONDS = 1.0

# User agent string
USER_AGENT = "RxDsec-CLI/1.0 (Offline Coding Agent; +https://github.com/rxdsec)"

# Default allowed domains (documentation sites)
DEFAULT_ALLOWED_DOMAINS = {
    # Documentation
    "docs.python.org",
    "docs.rust-lang.org",
    "doc.rust-lang.org",
    "go.dev",
    "pkg.go.dev",
    "nodejs.org",
    "developer.mozilla.org",
    "devdocs.io",
    
    # Package repositories
    "pypi.org",
    "npmjs.com",
    "crates.io",
    "rubygems.org",
    "packagist.org",
    "hex.pm",
    
    # Code hosting
    "github.com",
    "gitlab.com",
    "bitbucket.org",
    "raw.githubusercontent.com",
    
    # Q&A sites
    "stackoverflow.com",
    "stackexchange.com",
    
    # Other documentation
    "readthedocs.io",
    "readthedocs.org",
    
    # Search Engines
    "duckduckgo.com",
    "html.duckduckgo.com",
    "google.com",
    "bing.com",
}

# Domains that are always blocked
BLOCKED_DOMAINS = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
}


@dataclass
class RateLimiter:
    """Simple rate limiter for domain-based throttling"""
    _last_request: Dict[str, float] = field(default_factory=dict)
    
    def wait_if_needed(self, domain: str, min_interval: float = RATE_LIMIT_SECONDS):
        """Wait if necessary to respect rate limits"""
        now = time.time()
        last = self._last_request.get(domain, 0)
        
        elapsed = now - last
        if elapsed < min_interval:
            wait_time = min_interval - elapsed
            logger.debug(f"Rate limiting: waiting {wait_time:.2f}s for {domain}")
            time.sleep(wait_time)
        
        self._last_request[domain] = time.time()


# Global rate limiter
_rate_limiter = RateLimiter()


def create_session() -> "requests.Session":
    """Create a requests session with retry logic"""
    if not HAS_REQUESTS:
        raise ImportError("requests library not installed")
    
    session = requests.Session()
    
    # Configure retries
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"]
    )
    
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    # Set default headers
    session.headers.update({
        'User-Agent': USER_AGENT,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
    })
    
    return session


def is_domain_allowed(url: str, allowed_domains: Optional[Set[str]] = None) -> Tuple[bool, str]:
    """
    Check if a URL's domain is allowed.
    
    Args:
        url: URL to check
        allowed_domains: Set of allowed domain patterns
    
    Returns:
        Tuple of (is_allowed, reason)
    """
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        
        # Remove port number if present
        if ':' in domain:
            domain = domain.split(':')[0]
        
        # Check blocked domains
        if domain in BLOCKED_DOMAINS:
            return False, f"Domain {domain} is blocked (local/private address)"
        
        # Check allowed patterns
        allowed = allowed_domains or DEFAULT_ALLOWED_DOMAINS
        
        for pattern in allowed:
            # Exact match
            if domain == pattern:
                return True, ""
            
            # Subdomain match
            if domain.endswith('.' + pattern):
                return True, ""
            
            # Wildcard patterns
            if pattern.startswith('*.'):
                suffix = pattern[2:]
                if domain == suffix or domain.endswith('.' + suffix):
                    return True, ""
        
        return False, f"Domain {domain} is not in the allowed list"
        
    except Exception as e:
        return False, f"Invalid URL: {str(e)}"


def extract_text_from_html(html_content: str) -> str:
    """
    Extract readable text from HTML content.
    
    Args:
        html_content: Raw HTML string
    
    Returns:
        Cleaned text content
    """
    # Remove script and style elements
    text = re.sub(r'<script[^>]*>.*?</script>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    
    # Remove HTML comments
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
    
    # Replace common block elements with newlines
    text = re.sub(r'<(p|div|h[1-6]|li|br|tr)[^>]*>', '\n', text, flags=re.IGNORECASE)
    
    # Remove remaining tags
    text = re.sub(r'<[^>]+>', '', text)
    
    # Decode HTML entities
    text = html.unescape(text)
    
    # Clean up whitespace
    lines = [line.strip() for line in text.split('\n')]
    lines = [line for line in lines if line]
    text = '\n'.join(lines)
    
    # Collapse multiple spaces
    text = re.sub(r'[ \t]+', ' ', text)
    
    return text.strip()


def extract_code_blocks(html_content: str) -> List[str]:
    """
    Extract code blocks from HTML content.
    
    Args:
        html_content: Raw HTML string
    
    Returns:
        List of code block contents
    """
    code_blocks = []
    
    # Find <pre><code> blocks
    pre_code_pattern = r'<pre[^>]*>\s*<code[^>]*>(.*?)</code>\s*</pre>'
    for match in re.finditer(pre_code_pattern, html_content, flags=re.DOTALL | re.IGNORECASE):
        code = html.unescape(match.group(1))
        code = re.sub(r'<[^>]+>', '', code)  # Remove any inner tags
        code_blocks.append(code.strip())
    
    # Find standalone <code> blocks
    code_pattern = r'<code[^>]*>(.*?)</code>'
    for match in re.finditer(code_pattern, html_content, flags=re.DOTALL | re.IGNORECASE):
        code = html.unescape(match.group(1))
        code = re.sub(r'<[^>]+>', '', code)
        if len(code) > 10:  # Only include substantial code blocks
            code_blocks.append(code.strip())
    
    return code_blocks


@tool(
    name="webfetch",
    description="Fetch content from a URL with rate limiting, domain filtering, and content extraction.",
    category="web"
)
def webfetch(
    url: str,
    method: str = "GET",
    headers: Optional[str] = None,
    data: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT,
    extract_text: bool = True,
    extract_code: bool = False,
    workspace: Optional[Path] = None,
    permissions=None
) -> ToolResult:
    """
    Fetch content from a URL with safety features.
    
    Features:
    - Domain whitelisting
    - Rate limiting (1 request/second per domain)
    - Content extraction (text/code from HTML)
    - Automatic retry with backoff
    
    Args:
        url: URL to fetch
        method: HTTP method (GET, POST, etc.)
        headers: Additional headers as "Key: Value, Key2: Value2"
        data: Request body for POST/PUT
        timeout: Request timeout in seconds
        extract_text: If True, extract readable text from HTML
        extract_code: If True, also extract code blocks
        workspace: Working directory (unused but accepted)
        permissions: Permissions engine
    
    Returns:
        ToolResult with fetched content
    """
    if not HAS_REQUESTS:
        return ToolResult.fail(
            error="requests library not installed. Run: pip install requests",
            status=ToolStatus.FAILURE
        )
    
    try:
        # Validate URL
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        parsed = urlparse(url)
        if not parsed.netloc:
            return ToolResult.fail(
                error=f"Invalid URL: {url}",
                status=ToolStatus.VALIDATION_ERROR
            )
        
        domain = parsed.netloc.lower()
        
        # Check domain allowlist
        allowed, reason = is_domain_allowed(url)
        if not allowed:
            return ToolResult.fail(
                error=reason,
                status=ToolStatus.PERMISSION_DENIED,
                domain=domain
            )
        
        # Apply rate limiting
        _rate_limiter.wait_if_needed(domain)
        
        # Parse custom headers
        custom_headers = {}
        if headers:
            for pair in headers.split(','):
                if ':' in pair:
                    key, value = pair.split(':', 1)
                    custom_headers[key.strip()] = value.strip()
        
        # Create session and make request
        session = create_session()
        session.headers.update(custom_headers)
        
        # Prepare request kwargs
        request_kwargs = {
            'timeout': timeout,
            'stream': True,  # Stream to check size
            'allow_redirects': True,
        }
        
        if data and method.upper() in ('POST', 'PUT', 'PATCH'):
            # Try to parse as JSON
            try:
                request_kwargs['json'] = json.loads(data)
            except json.JSONDecodeError:
                request_kwargs['data'] = data
        
        # Make request
        response = session.request(method.upper(), url, **request_kwargs)
        
        # Check response size
        content_length = response.headers.get('Content-Length')
        if content_length and int(content_length) > MAX_RESPONSE_SIZE:
            return ToolResult.fail(
                error=f"Response too large: {int(content_length) / 1024 / 1024:.2f}MB",
                status=ToolStatus.VALIDATION_ERROR
            )
        
        # Read content with size limit
        content_parts = []
        total_size = 0
        for chunk in response.iter_content(chunk_size=8192, decode_unicode=True):
            if isinstance(chunk, bytes):
                chunk = chunk.decode('utf-8', errors='replace')
            content_parts.append(chunk)
            total_size += len(chunk)
            if total_size > MAX_RESPONSE_SIZE:
                break
        
        content = ''.join(content_parts)
        
        # Check status code
        if response.status_code >= 400:
            return ToolResult.fail(
                error=f"HTTP {response.status_code}: {response.reason}",
                output=content[:1000],
                status=ToolStatus.FAILURE,
                status_code=response.status_code
            )
        
        # Process content based on type
        content_type = response.headers.get('Content-Type', '').lower()
        
        result_content = content
        code_blocks = []
        
        if 'text/html' in content_type:
            if extract_code:
                code_blocks = extract_code_blocks(content)
            
            if extract_text:
                result_content = extract_text_from_html(content)
        
        elif 'application/json' in content_type:
            # Pretty-print JSON
            try:
                json_data = json.loads(content)
                result_content = json.dumps(json_data, indent=2)
            except:
                pass
        
        # Truncate if too long
        if len(result_content) > MAX_CONTENT_LENGTH:
            result_content = result_content[:MAX_CONTENT_LENGTH] + "\n\n... (content truncated)"
        
        # Build output
        output_parts = [result_content]
        
        if code_blocks:
            output_parts.append("\n\n=== CODE BLOCKS ===")
            for i, block in enumerate(code_blocks[:5], 1):  # Limit to 5 blocks
                output_parts.append(f"\n--- Block {i} ---\n{block[:2000]}")
        
        output = '\n'.join(output_parts)
        
        return ToolResult.ok(
            output=output,
            url=url,
            status_code=response.status_code,
            content_type=content_type,
            content_length=len(content),
            code_blocks_found=len(code_blocks) if extract_code else 0
        )
        
    except requests.Timeout:
        return ToolResult.fail(
            error=f"Request timed out after {timeout} seconds",
            status=ToolStatus.TIMEOUT
        )
    except requests.ConnectionError as e:
        return ToolResult.fail(
            error=f"Connection error: {str(e)}",
            status=ToolStatus.FAILURE
        )
    except requests.RequestException as e:
        return ToolResult.fail(
            error=f"Request error: {str(e)}",
            status=ToolStatus.FAILURE
        )
    except Exception as e:
        logger.exception(f"Error fetching URL: {url}")
        return ToolResult.fail(
            error=f"Error: {str(e)}",
            status=ToolStatus.FAILURE
        )


@tool(
    name="web_search",
    description="Search the web using DuckDuckGo (No API key required).",
    category="web"
)
def web_search(
    query: str,
    num_results: int = 5,
    type_filter: Optional[str] = None,
    workspace: Optional[Path] = None,
    permissions=None,
    **kwargs
) -> ToolResult:
    """
    Search the web using DuckDuckGo HTML interface.
    
    Args:
        query: Search query
        num_results: Number of results to return
        workspace: Working directory
        permissions: Permissions engine
    
    Returns:
        ToolResult with search results
    """
    if not HAS_REQUESTS:
        return ToolResult.fail(
            error="requests library not installed. Run: pip install requests",
            status=ToolStatus.FAILURE
        )
    
    try:
        # Handle type_filter
        if type_filter:
            tf = type_filter.lower()
            filter_map = {
                'github': 'site:github.com',
                'stackoverflow': 'site:stackoverflow.com',
                'reddit': 'site:reddit.com',
                'pypi': 'site:pypi.org',
                'python': 'site:docs.python.org',
                'readthedocs': 'site:readthedocs.io'
            }
            if tf in filter_map:
                query += f" {filter_map[tf]}"
            else:
                # Treat as generic site filter
                query += f" site:{tf}"

        url = "https://html.duckduckgo.com/html/"
        
        # Apply rate limiting
        _rate_limiter.wait_if_needed("duckduckgo.com")
        
        session = create_session()
        
        # Post request simulates a form submission
        response = session.post(
            url, 
            data={'q': query}, 
            headers={
                'User-Agent': USER_AGENT,
                'Referer': 'https://html.duckduckgo.com/'
            },
            timeout=DEFAULT_TIMEOUT
        )
        response.raise_for_status()
        
        content = response.text
        
        # Simple regex parsing for HTML results
        # Look for result title link and snippet
        results = []
        
        # Pattern for result blocks
        # This is a heuristic; DDG HTML structure might change but this usually works for the html version
        # We look for result__a for title/link and result__snippet for description
        
        # Extract all result blocks first roughly
        import re
        
        # Find all snippets
        snippets = re.findall(r'<a[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>', content, re.DOTALL)
        
        # Find all titles and links
        # <a class="result__a" href="...">Title</a>
        links_titles = re.findall(r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', content, re.DOTALL)
        
        # Clean up text
        def clean_text(t):
            return html.unescape(re.sub(r'<[^>]+>', '', t)).strip()
        
        count = 0
        output_lines = [f"Web Search Results for: {query}\n"]
        
        for i, (link, title_html) in enumerate(links_titles):
            if count >= num_results:
                break
                
            title = clean_text(title_html)
            snippet = clean_text(snippets[i]) if i < len(snippets) else "No description available."
            
            # Skip ad/internal links if possible
            if 'duckduckgo.com' in link:
                continue
                
            count += 1
            output_lines.append(f"{count}. {title}")
            output_lines.append(f"   URL: {link}")
            output_lines.append(f"   {snippet}\n")
            
            results.append({
                "title": title,
                "url": link,
                "snippet": snippet
            })
            
        if count == 0:
            return ToolResult.ok(
                output=f"No results found for query: {query}",
                results=[]
            )
            
        return ToolResult.ok(
            output="\n".join(output_lines),
            results=results
        )
        
    except Exception as e:
        return ToolResult.fail(
            error=f"Search failed: {str(e)}",
            status=ToolStatus.FAILURE
        )


@tool(
    name="download",
    description="Download a file from a URL and save it locally.",
    category="web"
)
def download(
    url: str,
    save_path: str,
    workspace: Optional[Path] = None,
    permissions=None
) -> ToolResult:
    """
    Download a file from URL.
    
    Args:
        url: URL to download from
        save_path: Local path to save the file
        workspace: Working directory
        permissions: Permissions engine
    
    Returns:
        ToolResult with download outcome
    """
    if not HAS_REQUESTS:
        return ToolResult.fail(
            error="requests library not installed",
            status=ToolStatus.FAILURE
        )
    
    try:
        # Check domain
        allowed, reason = is_domain_allowed(url)
        if not allowed:
            return ToolResult.fail(
                error=reason,
                status=ToolStatus.PERMISSION_DENIED
            )
        
        # Resolve save path
        if workspace:
            full_path = (workspace / save_path).resolve()
        else:
            full_path = Path(save_path).resolve()
        
        # Create parent directory
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Apply rate limiting
        domain = urlparse(url).netloc.lower()
        _rate_limiter.wait_if_needed(domain)
        
        # Download with streaming
        session = create_session()
        response = session.get(url, stream=True, timeout=60)
        response.raise_for_status()
        
        # Check size
        content_length = response.headers.get('Content-Length')
        if content_length and int(content_length) > MAX_RESPONSE_SIZE:
            return ToolResult.fail(
                error=f"File too large: {int(content_length) / 1024 / 1024:.2f}MB",
                status=ToolStatus.VALIDATION_ERROR
            )
        
        # Save file
        total_size = 0
        with open(full_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                total_size += len(chunk)
                if total_size > MAX_RESPONSE_SIZE:
                    f.close()
                    full_path.unlink()
                    return ToolResult.fail(
                        error=f"Download exceeded size limit",
                        status=ToolStatus.VALIDATION_ERROR
                    )
        
        return ToolResult.ok(
            output=f"Downloaded {total_size} bytes to {save_path}",
            path=str(full_path),
            size=total_size
        )
        
    except Exception as e:
        return ToolResult.fail(
            error=f"Download error: {str(e)}",
            status=ToolStatus.FAILURE
        )