# pipelines.py
import re
import html

class ArticleScraperPipeline:
    def process_item(self, item, spider):
        required_fields = ['link', 'title', 'published', 'body', 'domain']
        
        # Check for missing fields
        for field in required_fields:
            if not item.get(field):
                spider.logger.warning(f"Missing field '{field}' in item: {item}")
                item[field] = item.get(field, '')
        
        # Clean title
        if item['title']:
            item['title'] = self.clean_text(item['title'])
        
        # Clean body with comprehensive cleaning for pure content
        if item['body']:
            item['body'] = self.extract_pure_body(item['body'])
        
        return item
    
    def clean_text(self, text):
        """Basic text cleaning for titles and short text"""
        if not text:
            return ""
        
        # Decode HTML entities
        text = html.unescape(text)
        
        # Replace non-breaking spaces and other unicode spaces
        text = re.sub(r'\xa0+', ' ', text)
        text = re.sub(r'\u2000-\u200F', ' ', text)
        
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text)
        
        return text.strip()
    
    def extract_pure_body(self, text):
        """Extract pure body content, removing metadata and structural elements"""
        if not text:
            return ""
        
        # Decode HTML entities
        text = html.unescape(text)
        
        # Replace non-breaking spaces and other problematic unicode
        text = re.sub(r'\xa0+', ' ', text)
        text = re.sub(r'\u2000-\u200F', ' ', text)
        text = re.sub(r'\u2028|\u2029', '\n', text)
        
        # Remove author bio section (usually at the end)
        text = re.sub(r'\n\s*About the authors?.*$', '', text, flags=re.DOTALL | re.IGNORECASE)
        
        # Remove common article metadata patterns
        text = re.sub(r'^\s*Posted on.*?\n', '', text, flags=re.MULTILINE)
        text = re.sub(r'^\s*Published.*?\n', '', text, flags=re.MULTILINE)
        text = re.sub(r'^\s*Tags?:.*?\n', '', text, flags=re.MULTILINE)
        text = re.sub(r'^\s*Categories?:.*?\n', '', text, flags=re.MULTILINE)
        
        # Remove navigation elements
        text = re.sub(r'^\s*(Previous|Next|Home|Back to|Return to).*?\n', '', text, flags=re.MULTILINE | re.IGNORECASE)
        
        # Remove social sharing text
        text = re.sub(r'\b(Share on|Follow us|Subscribe to|Like this|Tweet this).*?\n', '', text, flags=re.IGNORECASE)
        
        # Remove common footer/header patterns
        text = re.sub(r'^\s*(Copyright|©|\(c\)).*?\n', '', text, flags=re.MULTILINE | re.IGNORECASE)
        text = re.sub(r'All rights reserved.*?\n', '', text, flags=re.IGNORECASE)
        
        # Convert code blocks to inline mentions (remove actual code)
        # Option 1: Remove code blocks entirely
        # text = re.sub(r'\[CODE\].*?\[/CODE\]', '', text, flags=re.DOTALL)
        
        # Option 2: Replace with simplified mentions (recommended)
        text = re.sub(r'\[CODE\]\s*#[^\n]*\n([^\[]*?)\[/CODE\]', r'[CODE EXAMPLE: \1...]', text, flags=re.DOTALL)
        text = re.sub(r'\[CODE\]\s*([^\n]{1,50}).*?\[/CODE\]', r'[CODE: \1...]', text, flags=re.DOTALL)
        text = re.sub(r'\[CODE\].*?\[/CODE\]', '[CODE BLOCK]', text, flags=re.DOTALL)
        
        # Clean up command-like patterns that aren't in code blocks
        text = re.sub(r'^\s*\$\s+.*?\n', '', text, flags=re.MULTILINE)
        text = re.sub(r'^\s*pip install.*?\n', '', text, flags=re.MULTILINE)
        text = re.sub(r'^\s*aws\s+.*?\n', '', text, flags=re.MULTILINE)
        text = re.sub(r'^\s*kubectl\s+.*?\n', '', text, flags=re.MULTILINE)
        text = re.sub(r'^\s*hyp\s+.*?\n', '', text, flags=re.MULTILINE)
        
        # Remove configuration examples and parameter lists
        text = re.sub(r'--[a-zA-Z-]+ [^\s]*', '', text)  # Remove CLI parameters
        text = re.sub(r'^\s*-\s+`[^`]+`.*?\n', '', text, flags=re.MULTILINE)  # Remove parameter descriptions
        
        # Remove inline code references for cleaner reading
        text = re.sub(r'`[^`]+`', '', text)
        
        # Remove URL references
        text = re.sub(r'https?://[^\s]+', '', text)
        
        # Remove file paths and technical references
        text = re.sub(r'/[a-zA-Z0-9/_.-]+', '', text)
        text = re.sub(r'[a-zA-Z0-9_-]+\.(py|js|yaml|yml|json|txt|md)', '', text)
        
        # Remove technical identifiers and version numbers
        text = re.sub(r'\b[a-zA-Z0-9_-]+::[a-zA-Z0-9_-]+\b', '', text)  # Remove :: references
        text = re.sub(r'\bv?\d+\.\d+\.\d+\b', '', text)  # Remove version numbers
        
        # Remove bracketed technical references
        text = re.sub(r'\[[^\]]*\]', '', text)
        
        # Clean up structural elements
        text = re.sub(r'^\s*Table \d+[.:]\s*.*?\n', '', text, flags=re.MULTILINE)
        text = re.sub(r'^\s*Figure \d+[.:]\s*.*?\n', '', text, flags=re.MULTILINE)
        text = re.sub(r'^\s*Listing \d+[.:]\s*.*?\n', '', text, flags=re.MULTILINE)
        
        # Remove table-like structures (pipe-separated content)
        lines = text.split('\n')
        cleaned_lines = []
        for line in lines:
            # Skip lines that look like table headers or separators
            if re.match(r'^\s*\|.*\|\s*$', line) or re.match(r'^\s*[-|]+\s*$', line):
                continue
            # Skip lines with multiple pipe characters (table rows)
            if line.count('|') > 2:
                continue
            cleaned_lines.append(line)
        text = '\n'.join(cleaned_lines)
        
        # Remove reference patterns
        text = re.sub(r'\bsee\s+[A-Z][^.]*\.\s*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\brefer to\s+[^.]*\.\s*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\bFor more information[^.]*\.\s*', '', text, flags=re.IGNORECASE)
        
        # Clean up excessive punctuation and special characters
        text = re.sub(r'[^\w\s.,!?;:()\'-]', ' ', text)
        
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text)  # Multiple spaces to single
        text = re.sub(r'\n\s+', '\n', text)  # Spaces after newlines
        text = re.sub(r'\s+\n', '\n', text)  # Spaces before newlines
        text = re.sub(r'\n{3,}', '\n\n', text)  # Excessive line breaks
        
        # Remove lines that are too short (likely fragments)
        lines = text.split('\n')
        meaningful_lines = []
        for line in lines:
            line = line.strip()
            if len(line) > 20 or (len(line) > 5 and '.' in line):  # Keep substantial lines or sentences
                meaningful_lines.append(line)
        
        text = '\n'.join(meaningful_lines)
        
        # Final cleanup
        text = text.strip()
        
        return text