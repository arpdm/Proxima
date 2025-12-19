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
    def folder_levels(self) -> List[str]:
        """Extract folder hierarchy levels."""
        parts = Path(self.filepath).parts
        levels = []
        for part in parts:
            if re.match(r'^\d{4}_', part):
                levels.append(part)
        return levels
    
    @property
    def folder_level_1(self) -> str:
        """Top-level folder (e.g., 0100_system)."""
        levels = self.folder_levels
        return levels[0] if len(levels) > 0 else "uncategorized"
    
    @property
    def folder_level_2(self) -> str:
        """Second-level folder (e.g., 0101_subsystem)."""
        levels = self.folder_levels
        return levels[1] if len(levels) > 1 else "none"
    
    @property
    def folder_level_3(self) -> str:
        """Third-level folder (e.g., 010101_component)."""
        levels = self.folder_levels
        return levels[2] if len(levels) > 2 else "none"

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
    # Group by folder levels
    by_level_1 = defaultdict(list)
    by_level_2 = defaultdict(list)
    by_level_3 = defaultdict(list)
    
    for req in requirements:
        by_level_1[req.folder_level_1].append(req)
        by_level_2[req.folder_level_2].append(req)
        by_level_3[req.folder_level_3].append(req)
    
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
            color: #e0e0e0;
            background: #0a0a0a;
        }
        .container {
            background: #1a1a1a;
            border-radius: 8px;
            padding: 30px;
            margin: 20px 0;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
        }
        h1 {
            color: #4fc3f7;
            border-bottom: 3px solid #2e7d32;
            padding-bottom: 10px;
            margin-bottom: 30px;
            font-weight: 300;
        }
        h2 {
            color: #81c784;
            margin-top: 30px;
            font-weight: 400;
        }
        .filters {
            background: #2a2a2a;
            padding: 20px;
            border-radius: 5px;
            margin: 20px 0;
            border-left: 4px solid #2e7d32;
        }
        .filter-group {
            margin: 15px 0;
        }
        .filter-group label {
            font-weight: bold;
            display: block;
            margin-bottom: 8px;
            color: #e0e0e0;
        }
        .filter-buttons {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }
        .filter-btn {
            padding: 8px 16px;
            border: 2px solid #4fc3f7;
            background: #333;
            color: #4fc3f7;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.9em;
        }
        .filter-btn:hover {
            background: #444;
        }
        .filter-btn.active {
            background: #4fc3f7;
            color: #0a0a0a;
        }
        .filter-btn.all {
            border-color: #666;
            color: #666;
        }
        .filter-btn.all.active {
            background: #666;
            color: #0a0a0a;
        }
        .filter-btn.none {
            border-color: #888;
            color: #888;
        }
        .filter-btn.none.active {
            background: #888;
            color: #0a0a0a;
        }
        .clear-filters {
            padding: 10px 20px;
            background: #d32f2f;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-weight: bold;
            margin-top: 10px;
        }
        .clear-filters:hover {
            background: #b71c1c;
        }
        .summary {
            background: #2a2a2a;
            padding: 15px;
            border-radius: 5px;
            margin: 20px 0;
            border-left: 4px solid #2e7d32;
        }
        .summary-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 10px;
        }
        .requirement {
            background: #2a2a2a;
            border: 1px solid #444;
            border-radius: 5px;
            padding: 20px;
            margin: 20px 0;
        }
        .requirement.hidden {
            display: none;
        }
        .req-header {
            background: linear-gradient(90deg, #0d47a1, #1b5e20);
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
            background: rgba(255,255,255,0.1);
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
            background: #333;
            border-radius: 3px;
        }
        .metadata-item {
            display: flex;
            flex-direction: column;
        }
        .metadata-label {
            font-weight: bold;
            font-size: 0.85em;
            color: #81c784;
            text-transform: uppercase;
        }
        .traceability {
            margin: 15px 0;
            padding: 10px;
            background: #333;
            border-left: 4px solid #ffc107;
            border-radius: 3px;
        }
        .trace-item {
            margin: 5px 0;
        }
        .trace-link {
            color: #4fc3f7;
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
        .status-draft { background: #f57c00; color: white; }
        .status-approved { background: #388e3c; color: white; }
        .status-review { background: #1976d2; color: white; }
        .priority-high { color: #d32f2f; font-weight: bold; }
        .priority-medium { color: #f57c00; }
        .priority-low { color: #81c784; }
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            font-size: 0.9em;
        }
        th, td {
            padding: 10px;
            text-align: left;
            border: 1px solid #444;
        }
        th {
            background: #1b5e20;
            color: white;
        }
        tr:nth-child(even) {
            background: #333;
        }
        tr.hidden {
            display: none;
        }
        .trace-list {
            font-size: 0.85em;
        }
        .results-count {
            padding: 10px;
            background: #333;
            border: 1px solid #444;
            border-radius: 4px;
            margin: 10px 0;
            color: #e0e0e0;
        }
        @media print {
            body {
                background: white;
                color: black;
            }
            .container {
                background: white;
                box-shadow: none;
            }
            .filters, .filter-buttons, .clear-filters {
                display: none;
            }
            .requirement, .summary, .filters {
                background: white;
                color: black;
            }
            .req-header {
                background: #f0f0f0;
                color: black;
            }
            .metadata {
                background: #f9f9f9;
            }
            .traceability {
                background: #fff3cd;
            }
            table th {
                background: #f0f0f0;
                color: black;
            }
            table tr:nth-child(even) {
                background: #f9f9f9;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Requirements Specification</h1>
        
        <div class="filters">
            <h3>Filter Requirements</h3>
            <div class="filter-group">
                <label>System Level:</label>
                <div class="filter-buttons">
                    <button class="filter-btn all active" onclick="filterByLevel('level1', 'all')">All</button>
"""
    
    for level1 in sorted(by_level_1.keys()):
        level1_name = level1.replace('_', ' ').title()
        html += f'                    <button class="filter-btn" onclick="filterByLevel(\'level1\', \'{level1}\')">{level1_name} ({len(by_level_1[level1])})</button>\n'
    
    html += """
                </div>
            </div>
            
            <div class="filter-group">
                <label>Subsystem Level:</label>
                <div class="filter-buttons">
                    <button class="filter-btn all active" onclick="filterByLevel('level2', 'all')">All</button>
                    <button class="filter-btn none active" onclick="filterByLevel('level2', 'none')">None</button>
"""
    
    for level2 in sorted(by_level_2.keys()):
        if level2 != "none":
            level2_name = level2.replace('_', ' ').title()
            html += f'                    <button class="filter-btn" onclick="filterByLevel(\'level2\', \'{level2}\')">{level2_name} ({len(by_level_2[level2])})</button>\n'
    
    html += """
                </div>
            </div>
            
            <div class="filter-group">
                <label>Component Level:</label>
                <div class="filter-buttons">
                    <button class="filter-btn all active" onclick="filterByLevel('level3', 'all')">All</button>
                    <button class="filter-btn none active" onclick="filterByLevel('level3', 'none')">None</button>
"""
    
    for level3 in sorted(by_level_3.keys()):
        if level3 != "none":
            level3_name = level3.replace('_', ' ').title()
            html += f'                    <button class="filter-btn" onclick="filterByLevel(\'level3\', \'{level3}\')">{level3_name} ({len(by_level_3[level3])})</button>\n'
    
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
                    <th>System</th>
                    <th>Subsystem</th>
                    <th>Component</th>
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
        level1_name = req.folder_level_1.replace('_', ' ').title()
        level2_name = req.folder_level_2.replace('_', ' ').title() if req.folder_level_2 != "none" else "-"
        level3_name = req.folder_level_3.replace('_', ' ').title() if req.folder_level_3 != "none" else "-"
        parent_link = f'<a href="#req-{req.parent}" class="trace-link">{req.parent}</a>' if req.parent else '-'
        
        children_links = '-'
        if req.children:
            child_list = [f'<a href="#req-{child}" class="trace-link">{child}</a>' for child in req.children]
            children_links = '<span class="trace-list">' + ', '.join(child_list) + '</span>'
        
        html += f"""
                <tr data-level1="{req.folder_level_1}" data-level2="{req.folder_level_2}" data-level3="{req.folder_level_3}" data-status="{req.status}" data-priority="{req.priority}">
                    <td><a href="#req-{req.id}" class="trace-link">{req.id}</a></td>
                    <td>{req.title}</td>
                    <td>{req.category}</td>
                    <td>{level1_name}</td>
                    <td>{level2_name}</td>
                    <td>{level3_name}</td>
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
        level1_name = req.folder_level_1.replace('_', ' ').title()
        level2_name = req.folder_level_2.replace('_', ' ').title() if req.folder_level_2 != "none" else ""
        level3_name = req.folder_level_3.replace('_', ' ').title() if req.folder_level_3 != "none" else ""
        folder_tag = f"{level1_name}"
        if level2_name:
            folder_tag += f" > {level2_name}"
        if level3_name:
            folder_tag += f" > {level3_name}"
        
        html += f"""
            <div id="req-{req.id}" class="requirement" data-level1="{req.folder_level_1}" data-level2="{req.folder_level_2}" data-level3="{req.folder_level_3}" data-status="{req.status}" data-priority="{req.priority}">
                <div class="req-header">
                    <div class="req-id">{req.id}</div>
                    <div>{req.title}</div>
                    <div class="req-folder-tag">{folder_tag}</div>
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
            html += '                <div class="traceability">\n                    <h4>Traceability</h4>\n'
            
            if req.parent:
                html += f'                    <div class="trace-item"><strong>Parent:</strong> <a href="#req-{req.parent}" class="trace-link">{req.parent}</a>'
                if req.parent in req_map:
                    html += f' - {req_map[req.parent].title}'
                html += '</div>\n'
            
            if ancestors:
                html += '                    <div class="trace-item"><strong>All Ancestors:</strong> '
                ancestor_links = [f'<a href="#req-{aid}" class="trace-link">{aid}</a>' for aid in reversed(ancestors)]
                html += ' → '.join(ancestor_links)
                html += '</div>\n'
            
            if req.children:
                html += '                    <div class="trace-item"><strong>Children:</strong> '
                child_links = []
                for child_id in req.children:
                    link = f'<a href="#req-{child_id}" class="trace-link">{child_id}</a>'
                    if child_id in req_map:
                        link += f' ({req_map[child_id].title})'
                    child_links.append(link)
                html += ', '.join(child_links)
                html += '</div>\n'
            
            if descendants:
                html += f'                    <div class="trace-item"><strong>All Descendants:</strong> {len(descendants)} requirement(s)</div>\n'
            
            html += '                </div>\n'
        
        html += f"""
                {content_html}
            </div>
"""
    
    html += """
        </div>
    </div>
    
    <script>
        let activeFilters = {
            level1: 'all',
            level2: 'all',
            level3: 'all',
            status: 'all',
            priority: 'all'
        };
        
        function updateFilterButtons(filterType, value) {
            const buttons = document.querySelectorAll(`.filter-btn[onclick*="${filterType}"]`);
            buttons.forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');
        }
        
        function filterByLevel(level, value) {
            activeFilters[level] = value;
            updateFilterButtons('filterByLevel', value);
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
                const level1 = req.dataset.level1;
                const level2 = req.dataset.level2;
                const level3 = req.dataset.level3;
                const status = req.dataset.status;
                const priority = req.dataset.priority;
                
                const level1Match = activeFilters.level1 === 'all' || level1 === activeFilters.level1;
                const level2Match = activeFilters.level2 === 'all' || (activeFilters.level2 === 'none' && level2 === 'none') || level2 === activeFilters.level2;
                const level3Match = activeFilters.level3 === 'all' || (activeFilters.level3 === 'none' && level3 === 'none') || level3 === activeFilters.level3;
                const statusMatch = activeFilters.status === 'all' || status === activeFilters.status;
                const priorityMatch = activeFilters.priority === 'all' || priority === activeFilters.priority;
                
                if (level1Match && level2Match && level3Match && statusMatch && priorityMatch) {
                    req.classList.remove('hidden');
                    visibleCount++;
                } else {
                    req.classList.add('hidden');
                }
            });
            
            tableRows.forEach(row => {
                const level1 = row.dataset.level1;
                const level2 = row.dataset.level2;
                const level3 = row.dataset.level3;
                const status = row.dataset.status;
                const priority = row.dataset.priority;
                
                const level1Match = activeFilters.level1 === 'all' || level1 === activeFilters.level1;
                const level2Match = activeFilters.level2 === 'all' || (activeFilters.level2 === 'none' && level2 === 'none') || level2 === activeFilters.level2;
                const level3Match = activeFilters.level3 === 'all' || (activeFilters.level3 === 'none' && level3 === 'none') || level3 === activeFilters.level3;
                const statusMatch = activeFilters.status === 'all' || status === activeFilters.status;
                const priorityMatch = activeFilters.priority === 'all' || priority === activeFilters.priority;
                
                if (level1Match && level2Match && level3Match && statusMatch && priorityMatch) {
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
                level1: 'all',
                level2: 'all',
                level3: 'all',
                status: 'all',
                priority: 'all'
            };
            
            document.querySelectorAll('.filter-btn').forEach(btn => {
                btn.classList.remove('active');
            });
            
            document.querySelectorAll('.filter-btn.all').forEach(btn => {
                btn.classList.add('active');
            });
            
            document.querySelectorAll('.filter-btn.none').forEach(btn => {
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
    requirements = collect_requirements('requirements')
    
    print(f"Found {len(requirements)} requirements")
    
    req_map = build_traceability(requirements)
    
    with_parents = sum(1 for r in requirements if r.parent)
    with_children = sum(1 for r in requirements if r.children)
    print(f"Requirements with parents: {with_parents}")
    print(f"Requirements with children: {with_children}")
    
    html_content = generate_html(requirements, req_map)
    
    with open('docs/requirements.html', 'w', encoding='utf-8') as f:
        f.write(html_content)
    print("Generated: requirements.html")
    

if __name__ == '__main__':
    main()