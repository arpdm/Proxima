import os
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional
from collections import defaultdict
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
    parent: Optional[str] = None  # Parent requirement ID
    children: List[str] = field(default_factory=list)  # Child requirement IDs
    
    @property
    def folder_category(self) -> str:
        """Extract category from folder structure."""
        parts = Path(self.filepath).parts
        # Find the top-level category folder (e.g., 0100_system)
        for part in parts:
            if re.match(r'^\d{4}_', part):
                return part
        return "uncategorized"

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
                folder=md_file.parent.name,
                parent=metadata.get('parent', None)
            )
            requirements.append(req)
    
    return sorted(requirements, key=lambda x: x.id)

def build_traceability(requirements: List[Requirement]) -> Dict[str, Requirement]:
    """Build parent-child relationships between requirements."""
    req_map = {req.id: req for req in requirements}
    
    # Build children lists
    for req in requirements:
        if req.parent and req.parent in req_map:
            req_map[req.parent].children.append(req.id)
    
    return req_map

def get_all_descendants(req_id: str, req_map: Dict[str, Requirement], visited: Set[str] = None) -> List[str]:
    """Get all descendant requirements recursively."""
    if visited is None:
        visited = set()
    
    if req_id in visited or req_id not in req_map:
        return []
    
    visited.add(req_id)
    descendants = []
    
    for child_id in req_map[req_id].children:
        descendants.append(child_id)
        descendants.extend(get_all_descendants(child_id, req_map, visited))
    
    return descendants

def get_all_ancestors(req_id: str, req_map: Dict[str, Requirement], visited: Set[str] = None) -> List[str]:
    """Get all ancestor requirements recursively."""
    if visited is None:
        visited = set()
    
    if req_id in visited or req_id not in req_map:
        return []
    
    visited.add(req_id)
    req = req_map[req_id]
    ancestors = []
    
    if req.parent and req.parent in req_map:
        ancestors.append(req.parent)
        ancestors.extend(get_all_ancestors(req.parent, req_map, visited))
    
    return ancestors

def generate_html(requirements: List[Requirement], req_map: Dict[str, Requirement]) -> str:
    """Generate HTML report from requirements."""
    # Group by folder category
    by_folder = defaultdict(list)
    for req in requirements:
        by_folder[req.folder_category].append(req)
    
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
            max-width: 1400px;
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
            border-bottom: 2px solid #ecf0f1;
            padding-bottom: 8px;
        }
        h3 {
            color: #7f8c8d;
            margin-top: 25px;
        }
        .toc {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 5px;
            margin: 20px 0;
        }
        .toc ul {
            list-style: none;
            padding-left: 20px;
        }
        .toc a {
            color: #3498db;
            text-decoration: none;
        }
        .toc a:hover {
            text-decoration: underline;
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
        .folder-section {
            margin: 30px 0;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 8px;
        }
        .folder-header {
            background: #34495e;
            color: white;
            padding: 15px;
            margin: -20px -20px 20px -20px;
            border-radius: 8px 8px 0 0;
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
        .traceability {
            margin: 15px 0;
            padding: 10px;
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            border-radius: 3px;
        }
        .trace-item {
            margin: 5px 0;
        }
        .trace-link {
            color: #3498db;
            text-decoration: none;
            font-weight: 500;
        }
        .trace-link:hover {
            text-decoration: underline;
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
            font-size: 0.9em;
        }
        th, td {
            padding: 10px;
            text-align: left;
            border: 1px solid #ddd;
        }
        th {
            background: #34495e;
            color: white;
            position: sticky;
            top: 0;
        }
        tr:nth-child(even) {
            background: #f8f9fa;
        }
        .trace-matrix {
            overflow-x: auto;
        }
        .trace-matrix table {
            font-size: 0.8em;
        }
        .trace-matrix th {
            writing-mode: vertical-rl;
            text-orientation: mixed;
            min-width: 30px;
        }
        .trace-cell-yes {
            background: #27ae60;
            color: white;
            text-align: center;
            font-weight: bold;
        }
        .trace-cell-no {
            background: #ecf0f1;
        }
        @media print {
            .folder-section {
                page-break-before: always;
            }
        }
    </style>
</head>
<body>
    <h1>Requirements Specification</h1>
    
    <div class="toc">
        <h2>Table of Contents</h2>
        <ul>
            <li><a href="#summary">Summary</a></li>
            <li><a href="#requirements-table">Requirements Table</a></li>
            <li><a href="#traceability-matrix">Traceability Matrix</a></li>
            <li><a href="#by-category">Requirements by Category</a>
                <ul>
"""
    
    for folder in sorted(by_folder.keys()):
        folder_name = folder.replace('_', ' ').title()
        html += f'                    <li><a href="#category-{folder}">{folder_name}</a></li>\n'
    
    html += """
                </ul>
            </li>
        </ul>
    </div>
    
    <div id="summary" class="summary">
        <h2>Summary</h2>
        <div class="summary-grid">
            <div><strong>Total Requirements:</strong> """ + str(len(requirements)) + """</div>
            <div><strong>Draft:</strong> """ + str(sum(1 for r in requirements if r.status == 'draft')) + """</div>
            <div><strong>Approved:</strong> """ + str(sum(1 for r in requirements if r.status == 'approved')) + """</div>
            <div><strong>High Priority:</strong> """ + str(sum(1 for r in requirements if r.priority == 'high')) + """</div>
        </div>
        <h3>By Category</h3>
        <div class="summary-grid">
"""
    
    for folder in sorted(by_folder.keys()):
        folder_name = folder.replace('_', ' ').title()
        count = len(by_folder[folder])
        html += f'            <div><strong>{folder_name}:</strong> {count}</div>\n'
    
    html += """
        </div>
    </div>
    
    <h2 id="requirements-table">Requirements Table</h2>
    <table>
        <thead>
            <tr>
                <th>ID</th>
                <th>Title</th>
                <th>Category</th>
                <th>Folder</th>
                <th>Status</th>
                <th>Priority</th>
                <th>Owner</th>
                <th>Parent</th>
                <th>Children</th>
            </tr>
        </thead>
        <tbody>
"""
    
    for req in requirements:
        folder_name = req.folder_category.replace('_', ' ').title()
        parent_link = f'<a href="#req-{req.parent}" class="trace-link">{req.parent}</a>' if req.parent else '-'
        children_links = ', '.join([f'<a href="#req-{child}" class="trace-link">{child}</a>' for child in req.children]) if req.children else '-'
        
        html += f"""
            <tr>
                <td><a href="#req-{req.id}" class="trace-link">{req.id}</a></td>
                <td>{req.title}</td>
                <td>{req.category}</td>
                <td>{folder_name}</td>
                <td><span class="status status-{req.status}">{req.status}</span></td>
                <td class="priority-{req.priority}">{req.priority}</td>
                <td>{req.owner}</td>
                <td>{parent_link}</td>
                <td>{children_links}</td>
            </tr>
"""
    
    html += """
        </tbody>
    </table>
    
    <h2 id="traceability-matrix">Traceability Matrix</h2>
    <div class="trace-matrix">
        <table>
            <thead>
                <tr>
                    <th>From \ To</th>
"""
    
    for req in requirements:
        html += f'                    <th>{req.id}</th>\n'
    
    html += """
                </tr>
            </thead>
            <tbody>
"""
    
    for req_from in requirements:
        html += f'                <tr>\n                    <th>{req_from.id}</th>\n'
        descendants = get_all_descendants(req_from.id, req_map)
        
        for req_to in requirements:
            if req_to.id in descendants:
                html += '                    <td class="trace-cell-yes">✓</td>\n'
            else:
                html += '                    <td class="trace-cell-no"></td>\n'
        
        html += '                </tr>\n'
    
    html += """
            </tbody>
        </table>
    </div>
    
    <h2 id="by-category">Requirements by Category</h2>
"""
    
    for folder in sorted(by_folder.keys()):
        folder_name = folder.replace('_', ' ').title()
        folder_reqs = by_folder[folder]
        
        html += f"""
    <div id="category-{folder}" class="folder-section">
        <div class="folder-header">
            <h2>{folder_name}</h2>
            <div>{len(folder_reqs)} requirements</div>
        </div>
"""
        
        for req in folder_reqs:
            content_html = markdown.markdown(req.content)
            ancestors = get_all_ancestors(req.id, req_map)
            descendants = get_all_descendants(req.id, req_map)
            
            html += f"""
        <div id="req-{req.id}" class="requirement">
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
"""
            
            if req.parent or req.children or ancestors or descendants:
                html += '            <div class="traceability">\n                <h4>Traceability</h4>\n'
                
                if req.parent:
                    html += f'                <div class="trace-item"><strong>Parent:</strong> <a href="#req-{req.parent}" class="trace-link">{req.parent}</a>'
                    if req.parent in req_map:
                        html += f' - {req_map[req.parent].title}'
                    html += '</div>\n'
                
                if ancestors:
                    html += '                <div class="trace-item"><strong>All Ancestors:</strong> '
                    ancestor_links = [f'<a href="#req-{aid}" class="trace-link">{aid}</a>' for aid in reversed(ancestors)]
                    html += ' → '.join(ancestor_links)
                    html += '</div>\n'
                
                if req.children:
                    html += '                <div class="trace-item"><strong>Children:</strong> '
                    child_links = []
                    for child_id in req.children:
                        link = f'<a href="#req-{child_id}" class="trace-link">{child_id}</a>'
                        if child_id in req_map:
                            link += f' ({req_map[child_id].title})'
                        child_links.append(link)
                    html += ', '.join(child_links)
                    html += '</div>\n'
                
                if descendants:
                    html += f'                <div class="trace-item"><strong>All Descendants:</strong> {len(descendants)} requirement(s)</div>\n'
                
                html += '            </div>\n'
            
            html += f"""
            {content_html}
        </div>
"""
        
        html += '    </div>\n'
    
    html += """
</body>
</html>
"""
    return html

def main():
    # Collect requirements from current directory
    requirements = collect_requirements('.')
    
    print(f"Found {len(requirements)} requirements")
    
    # Build traceability
    req_map = build_traceability(requirements)
    
    # Print traceability stats
    with_parents = sum(1 for r in requirements if r.parent)
    with_children = sum(1 for r in requirements if r.children)
    print(f"Requirements with parents: {with_parents}")
    print(f"Requirements with children: {with_children}")
    
    # Generate HTML
    html_content = generate_html(requirements, req_map)
    
    # Save HTML
    with open('requirements_report.html', 'w', encoding='utf-8') as f:
        f.write(html_content)
    print("Generated: requirements_report.html")
    
    # Generate PDF
    HTML(string=html_content).write_pdf('requirements_report.pdf')
    print("Generated: requirements_report.pdf")

if __name__ == '__main__':
    main()