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
    parent: Optional[str] = None
    children: List[str] = field(default_factory=list)
    
    @property
    def folder_category(self) -> str:
        """Extract category from folder structure."""
        parts = Path(self.filepath).parts
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
        
        if 'id' in metadata:
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
        }
        .filters {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 5px;
            margin: 20px 0;
            border: 2px solid #dee2e6;
        }
        .filter-group {
            margin: 15px 0;
        }
        .filter-group label {
            font-weight: bold;
            display: block;
            margin-bottom: 8px;
            color: #495057;
        }
        .filter-buttons {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }
        .filter-btn {
            padding: 8px 16px;
            border: 2px solid #3498db;
            background: white;
            color: #3498db;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.9em;
            transition: all 0.2s;
        }
        .filter-btn:hover {
            background: #e3f2fd;
        }
        .filter-btn.active {
            background: #3498db;
            color: white;
        }
        .filter-btn.all {
            border-color: #6c757d;
            color: #6c757d;
        }
        .filter-btn.all.active {
            background: #6c757d;
            color: white;
        }
        .clear-filters {
            padding: 10px 20px;
            background: #e74c3c;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-weight: bold;
            margin-top: 10px;
        }
        .clear-filters:hover {
            background: #c0392b;
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
            transition: opacity 0.3s;
        }
        .requirement.hidden {
            display: none;
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
        .req-folder-tag {
            display: inline-block;
            padding: 4px 8px;
            background: rgba(255,255,255,0.2);
            border-radius: 3px;
            font-size: 0.8em;
            margin-top: 5px;
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
        }
        tr:nth-child(even) {
            background: #f8f9fa;
        }
        tr.hidden {
            display: none;
        }
        .trace-list {
            font-size: 0.85em;
        }
        .results-count {
            padding: 10px;
            background: #d1ecf1;
            border: 1px solid #bee5eb;
            border-radius: 4px;
            margin: 10px 0;
            color: #0c5460;
        }
        @media print {
            .filters, .filter-buttons, .clear-filters {
                display: none;
            }
        }
    </style>
</head>
<body>
    <h1>Requirements Specification</h1>
    
    <div class="filters">
        <h3>Filter Requirements</h3>
        <div class="filter-group">
            <label>Folder Category:</label>
            <div class="filter-buttons">
                <button class="filter-btn all active" onclick="filterByFolder('all')">All</button>
"""
    
    for folder in sorted(by_folder.keys()):
        folder_name = folder.replace('_', ' ').title()
        html += f'                <button class="filter-btn" onclick="filterByFolder(\'{folder}\')">{folder_name} ({len(by_folder[folder])})</button>\n'
    
    html += """
            </div>
        </div>
        
        <div class="filter-group">
            <label>Status:</label>
            <div class="filter-buttons">
                <button class="filter-btn all active" onclick="filterByStatus('all')">All</button>
                <button class="filter-btn" onclick="filterByStatus('draft')">Draft</button>
                <button class="filter-btn" onclick="filterByStatus('approved')">Approved</button>
                <button class="filter-btn" onclick="filterByStatus('review')">Review</button>
            </div>
        </div>
        
        <div class="filter-group">
            <label>Priority:</label>
            <div class="filter-buttons">
                <button class="filter-btn all active" onclick="filterByPriority('all')">All</button>
                <button class="filter-btn" onclick="filterByPriority('high')">High</button>
                <button class="filter-btn" onclick="filterByPriority('medium')">Medium</button>
                <button class="filter-btn" onclick="filterByPriority('low')">Low</button>
            </div>
        </div>
        
        <button class="clear-filters" onclick="clearAllFilters()">Clear All Filters</button>
        <div class="results-count" id="results-count"></div>
    </div>
    
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
    <table id="requirements-table">
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
        
        children_links = '-'
        if req.children:
            child_list = [f'<a href="#req-{child}" class="trace-link">{child}</a>' for child in req.children]
            children_links = '<span class="trace-list">' + ', '.join(child_list) + '</span>'
        
        html += f"""
            <tr data-folder="{req.folder_category}" data-status="{req.status}" data-priority="{req.priority}">
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
    
    <h2>Detailed Requirements</h2>
    <div id="requirements-list">
"""
    
    for req in requirements:
        content_html = markdown.markdown(req.content)
        ancestors = get_all_ancestors(req.id, req_map)
        descendants = get_all_descendants(req.id, req_map)
        folder_name = req.folder_category.replace('_', ' ').title()
        
        html += f"""
        <div id="req-{req.id}" class="requirement" data-folder="{req.folder_category}" data-status="{req.status}" data-priority="{req.priority}">
            <div class="req-header">
                <div class="req-id">{req.id}</div>
                <div>{req.title}</div>
                <div class="req-folder-tag">{folder_name}</div>
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
    
    html += """
    </div>
    
    <script>
        let activeFilters = {
            folder: 'all',
            status: 'all',
            priority: 'all'
        };
        
        function updateFilterButtons(filterType, value) {
            const buttons = document.querySelectorAll(`.filter-btn[onclick*="${filterType}"]`);
            buttons.forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');
        }
        
        function filterByFolder(folder) {
            activeFilters.folder = folder;
            updateFilterButtons('filterByFolder', folder);
            applyFilters();
        }
        
        function filterByStatus(status) {
            activeFilters.status = status;
            updateFilterButtons('filterByStatus', status);
            applyFilters();
        }
        
        function filterByPriority(priority) {
            activeFilters.priority = priority;
            updateFilterButtons('filterByPriority', priority);
            applyFilters();
        }
        
        function applyFilters() {
            const requirements = document.querySelectorAll('.requirement');
            const tableRows = document.querySelectorAll('#requirements-table tbody tr');
            let visibleCount = 0;
            
            requirements.forEach(req => {
                const folder = req.dataset.folder;
                const status = req.dataset.status;
                const priority = req.dataset.priority;
                
                const folderMatch = activeFilters.folder === 'all' || folder === activeFilters.folder;
                const statusMatch = activeFilters.status === 'all' || status === activeFilters.status;
                const priorityMatch = activeFilters.priority === 'all' || priority === activeFilters.priority;
                
                if (folderMatch && statusMatch && priorityMatch) {
                    req.classList.remove('hidden');
                    visibleCount++;
                } else {
                    req.classList.add('hidden');
                }
            });
            
            tableRows.forEach(row => {
                const folder = row.dataset.folder;
                const status = row.dataset.status;
                const priority = row.dataset.priority;
                
                const folderMatch = activeFilters.folder === 'all' || folder === activeFilters.folder;
                const statusMatch = activeFilters.status === 'all' || status === activeFilters.status;
                const priorityMatch = activeFilters.priority === 'all' || priority === activeFilters.priority;
                
                if (folderMatch && statusMatch && priorityMatch) {
                    row.classList.remove('hidden');
                } else {
                    row.classList.add('hidden');
                }
            });
            
            document.getElementById('results-count').textContent = 
                `Showing ${visibleCount} of """ + str(len(requirements)) + """ requirements`;
        }
        
        function clearAllFilters() {
            activeFilters = {
                folder: 'all',
                status: 'all',
                priority: 'all'
            };
            
            document.querySelectorAll('.filter-btn').forEach(btn => {
                btn.classList.remove('active');
            });
            
            document.querySelectorAll('.filter-btn.all').forEach(btn => {
                btn.classList.add('active');
            });
            
            applyFilters();
        }
        
        // Initialize results count
        applyFilters();
    </script>
</body>
</html>
"""
    return html

def main():
    requirements = collect_requirements('.')
    
    print(f"Found {len(requirements)} requirements")
    
    req_map = build_traceability(requirements)
    
    with_parents = sum(1 for r in requirements if r.parent)
    with_children = sum(1 for r in requirements if r.children)
    print(f"Requirements with parents: {with_parents}")
    print(f"Requirements with children: {with_children}")
    
    html_content = generate_html(requirements, req_map)
    
    with open('requirements_report.html', 'w', encoding='utf-8') as f:
        f.write(html_content)
    print("Generated: requirements_report.html")
    
    HTML(string=html_content).write_pdf('requirements_report.pdf')
    print("Generated: requirements_report.pdf")

if __name__ == '__main__':
    main()