import os
import re
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict
import markdown
from weasyprint import HTML

@dataclass
class Requirement:
    id: str
    title: str
    source: str
    category: str
    status: str
    owner: str
    verify: str
    priority: str
    content: str
    filepath: str
    folder: str

def parse_frontmatter(content: str) -> Dict[str, str]:
    """Extract YAML frontmatter from markdown content."""
    pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
    match = re.match(pattern, content, re.DOTALL)
    
    if not match:
        return {}, content
    
    frontmatter_text, body = match.groups()
    metadata = {}
    
    for line in frontmatter_text.split('\n'):
        if ':' in line:
            key, value = line.split(':', 1)
            metadata[key.strip()] = value.strip()
    
    return metadata, body

def collect_requirements(base_path: str) -> List[Requirement]:
    """Recursively collect all requirement markdown files."""
    requirements = []
    base = Path(base_path)
    
    for md_file in base.rglob('*.md'):
        with open(md_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        metadata, body = parse_frontmatter(content)
        
        if 'id' in metadata:  # Only process files with requirement metadata
            req = Requirement(
                id=metadata.get('id', 'N/A'),
                title=metadata.get('title', 'N/A'),
                source=metadata.get('source', 'N/A'),
                category=metadata.get('category', 'N/A'),
                status=metadata.get('status', 'N/A'),
                owner=metadata.get('owner', 'N/A'),
                verify=metadata.get('verify', 'N/A'),
                priority=metadata.get('priority', 'N/A'),
                content=body,
                filepath=str(md_file),
                folder=md_file.parent.name
            )
            requirements.append(req)
    
    return sorted(requirements, key=lambda x: x.id)

def generate_html(requirements: List[Requirement]) -> str:
    """Generate HTML report from requirements."""
    html = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Requirements Specification</title>
    <style>
        body {
            font-family: 'Segoe UI', Arial, sans-serif;
            line-height: 1.6;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            color: #333;
        }
        h1 {
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }
        h2 {
            color: #34495e;
            margin-top: 30px;
        }
        .summary {
            background: #ecf0f1;
            padding: 15px;
            border-radius: 5px;
            margin: 20px 0;
        }
        .summary-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 10px;
        }
        .requirement {
            background: white;
            border: 1px solid #ddd;
            border-radius: 5px;
            padding: 20px;
            margin: 20px 0;
            page-break-inside: avoid;
        }
        .req-header {
            background: #3498db;
            color: white;
            padding: 10px;
            margin: -20px -20px 15px -20px;
            border-radius: 5px 5px 0 0;
        }
        .req-id {
            font-size: 1.2em;
            font-weight: bold;
        }
        .metadata {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 10px;
            margin: 15px 0;
            padding: 10px;
            background: #f8f9fa;
            border-radius: 3px;
        }
        .metadata-item {
            display: flex;
            flex-direction: column;
        }
        .metadata-label {
            font-weight: bold;
            font-size: 0.85em;
            color: #7f8c8d;
            text-transform: uppercase;
        }
        .status {
            display: inline-block;
            padding: 3px 8px;
            border-radius: 3px;
            font-size: 0.85em;
            font-weight: bold;
        }
        .status-draft { background: #f39c12; color: white; }
        .status-approved { background: #27ae60; color: white; }
        .status-review { background: #3498db; color: white; }
        .priority-high { color: #e74c3c; font-weight: bold; }
        .priority-medium { color: #f39c12; }
        .priority-low { color: #95a5a6; }
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }
        th, td {
            padding: 10px;
            text-align: left;
            border: 1px solid #ddd;
        }
        th {
            background: #34495e;
            color: white;
        }
        tr:nth-child(even) {
            background: #f8f9fa;
        }
    </style>
</head>
<body>
    <h1>Requirements Specification</h1>
    <div class="summary">
        <h2>Summary</h2>
        <div class="summary-grid">
            <div><strong>Total Requirements:</strong> """ + str(len(requirements)) + """</div>
            <div><strong>Draft:</strong> """ + str(sum(1 for r in requirements if r.status == 'draft')) + """</div>
            <div><strong>Approved:</strong> """ + str(sum(1 for r in requirements if r.status == 'approved')) + """</div>
            <div><strong>High Priority:</strong> """ + str(sum(1 for r in requirements if r.priority == 'high')) + """</div>
        </div>
    </div>
    
    <h2>Requirements Table</h2>
    <table>
        <thead>
            <tr>
                <th>ID</th>
                <th>Title</th>
                <th>Category</th>
                <th>Status</th>
                <th>Priority</th>
                <th>Owner</th>
                <th>Verification</th>
            </tr>
        </thead>
        <tbody>
"""
    
    for req in requirements:
        html += f"""
            <tr>
                <td>{req.id}</td>
                <td>{req.title}</td>
                <td>{req.category}</td>
                <td><span class="status status-{req.status}">{req.status}</span></td>
                <td class="priority-{req.priority}">{req.priority}</td>
                <td>{req.owner}</td>
                <td>{req.verify}</td>
            </tr>
"""
    
    html += """
        </tbody>
    </table>
    
    <h2>Detailed Requirements</h2>
"""
    
    for req in requirements:
        content_html = markdown.markdown(req.content)
        html += f"""
    <div class="requirement">
        <div class="req-header">
            <div class="req-id">{req.id}</div>
            <div>{req.title}</div>
        </div>
        <div class="metadata">
            <div class="metadata-item">
                <span class="metadata-label">Category</span>
                <span>{req.category}</span>
            </div>
            <div class="metadata-item">
                <span class="metadata-label">Status</span>
                <span class="status status-{req.status}">{req.status}</span>
            </div>
            <div class="metadata-item">
                <span class="metadata-label">Priority</span>
                <span class="priority-{req.priority}">{req.priority}</span>
            </div>
            <div class="metadata-item">
                <span class="metadata-label">Owner</span>
                <span>{req.owner}</span>
            </div>
            <div class="metadata-item">
                <span class="metadata-label">Verification</span>
                <span>{req.verify}</span>
            </div>
            <div class="metadata-item">
                <span class="metadata-label">Source</span>
                <span>{req.source}</span>
            </div>
        </div>
        {content_html}
    </div>
"""
    
    html += """
</body>
</html>
"""
    return html

def main():
    # Collect requirements from current directory
    requirements = collect_requirements('.')
    
    print(f"Found {len(requirements)} requirements")
    
    # Generate HTML
    html_content = generate_html(requirements)
    
    # Save HTML
    with open('requirements_report.html', 'w', encoding='utf-8') as f:
        f.write(html_content)
    print("Generated: requirements_report.html")
    
    # Generate PDF
    HTML(string=html_content).write_pdf('requirements_report.pdf')
    print("Generated: requirements_report.pdf")

if __name__ == '__main__':
    main()