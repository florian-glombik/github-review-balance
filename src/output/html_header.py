"""HTML header generation for OutputFormatter."""

from typing import Dict
from datetime import datetime


def _generate_html_header(self, open_prs_by_author: Dict[str, list] = None) -> str:
    """Generate HTML header with CSS styles."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    users_with_open_prs = set(open_prs_by_author.keys()) if open_prs_by_author else set()
    users_with_open_prs_json = str(list(users_with_open_prs)).replace("'", '"')

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GitHub Review Analysis - {self.username}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            line-height: 1.6;
            color: #333;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            min-height: 100vh;
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            padding: 40px;
        }}

        h1 {{
            color: #667eea;
            margin-bottom: 10px;
            font-size: 2.5em;
            text-align: center;
        }}

        h2 {{
            color: #667eea;
            margin-top: 40px;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 3px solid #667eea;
            font-size: 1.8em;
        }}

        h3 {{
            color: #764ba2;
            margin-top: 30px;
            margin-bottom: 15px;
            font-size: 1.3em;
        }}

        .timestamp {{
            text-align: center;
            color: #666;
            font-size: 0.9em;
            margin-bottom: 30px;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
        }}

        thead {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }}

        th {{
            padding: 15px;
            text-align: left;
            font-weight: 600;
            text-transform: uppercase;
            font-size: 0.85em;
            letter-spacing: 0.5px;
            cursor: pointer;
            user-select: none;
            position: relative;
            transition: background-color 0.2s ease;
        }}

        th:hover {{
            background-color: rgba(0, 0, 0, 0.1);
        }}

        th::after {{
            content: ' \u21c5';
            opacity: 0.3;
            font-size: 0.8em;
        }}

        th.sort-asc::after {{
            content: ' \u2191';
            opacity: 1;
        }}

        th.sort-desc::after {{
            content: ' \u2193';
            opacity: 1;
        }}

        td {{
            padding: 12px 15px;
            border-bottom: 1px solid #f0f0f0;
        }}

        tbody tr {{
            cursor: pointer;
            transition: background-color 0.2s ease;
        }}

        tbody tr:hover {{
            background-color: #f8f9fa;
        }}

        tbody tr.highlight {{
            animation: highlight-fade 2s ease-out;
        }}

        @keyframes highlight-fade {{
            0% {{
                background-color: #ffd700;
            }}
            100% {{
                background-color: transparent;
            }}
        }}

        .balance-positive {{
            color: #28a745;
            font-weight: 600;
        }}

        .balance-negative {{
            color: #dc3545;
            font-weight: 600;
        }}

        .balance-warning {{
            color: #ffc107;
            font-weight: 600;
        }}

        .balance-neutral {{
            color: #6c757d;
        }}

        .pr-list {{
            list-style: none;
            margin: 10px 0;
        }}

        .pr-item {{
            margin: 15px 0;
            padding: 0;
            background: #f8f9fa;
            border-left: 4px solid #667eea;
            border-radius: 4px;
        }}

        .pr-item-link {{
            display: block;
            padding: 15px;
            text-decoration: none;
            color: inherit;
        }}

        .pr-item-link:hover {{
            background: rgba(102, 126, 234, 0.05);
        }}

        .pr-item.priority-high {{
            border-left-color: #28a745;
            background: #e8f5e9;
        }}

        .pr-item.priority-medium {{
            border-left-color: #ffc107;
            background: #fff8e1;
        }}

        .pr-item.priority-low {{
            border-left-color: #dc3545;
            background: #ffebee;
        }}

        .pr-item.requested {{
            border-left-color: #17a2b8;
            background: #e0f7fa;
            border-width: 6px;
        }}

        .pr-title {{
            font-weight: 600;
            color: #333;
            margin-bottom: 5px;
        }}

        .pr-meta {{
            font-size: 0.9em;
            color: #666;
        }}

        .pr-link {{
            color: #667eea;
            text-decoration: none;
            word-break: break-all;
        }}

        .pr-link:hover {{
            text-decoration: underline;
        }}

        .author-section {{
            margin: 20px 0;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 8px;
            scroll-margin-top: 20px;
        }}

        .author-name {{
            font-size: 1.2em;
            font-weight: 600;
            margin-bottom: 10px;
        }}

        .author-link {{
            color: #667eea;
            text-decoration: none;
        }}

        .author-link:hover {{
            text-decoration: underline;
        }}

        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}

        .stat-card {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }}

        .stat-label {{
            font-size: 0.9em;
            opacity: 0.9;
            margin-bottom: 5px;
        }}

        .stat-value {{
            font-size: 2em;
            font-weight: 700;
        }}

        .badge {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.85em;
            font-weight: 600;
            margin-left: 8px;
        }}

        .badge-requested {{
            background: #17a2b8;
            color: white;
        }}

        .badge-reviews {{
            background: #6c757d;
            color: white;
        }}

        .badge-changes-requested {{
            background: #dc3545;
            color: white;
        }}

        .badge-ready-to-merge {{
            background: #28a745;
            color: white;
        }}

        .badge-developer-approved {{
            background: #007bff;
            color: white;
        }}

        .badge-maintainer-approved {{
            background: #6f42c1;
            color: white;
        }}

        .badge-re-review {{
            background: #fd7e14;
            color: white;
        }}

        .badge-ready-for-review {{
            background: #4caf50;
            color: white;
        }}

        .no-data {{
            text-align: center;
            padding: 40px;
            color: #999;
            font-style: italic;
        }}

        .detailed-section {{
            margin: 30px 0;
            padding: 20px;
            background: #fafafa;
            border-radius: 8px;
            border: 1px solid #e0e0e0;
        }}

        .metric-table {{
            width: 100%;
            margin: 15px 0;
        }}

        .metric-table td {{
            padding: 8px;
        }}

        .metric-table td:first-child {{
            font-weight: 600;
            width: 40%;
        }}

        .back-to-table {{
            display: inline-block;
            color: #667eea;
            text-decoration: none;
            font-size: 0.85em;
            opacity: 0.7;
            transition: opacity 0.2s ease;
            margin-right: 10px;
        }}

        .back-to-table:hover {{
            opacity: 1;
            text-decoration: underline;
        }}

        .settings-section {{
            background: #f8f9fa;
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
            border: 1px solid #e0e0e0;
        }}

        .settings-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 15px;
            margin-top: 15px;
        }}

        .setting-item {{
            display: flex;
            flex-direction: column;
        }}

        .setting-label {{
            font-weight: 600;
            color: #555;
            margin-bottom: 5px;
            font-size: 0.9em;
        }}

        .setting-value {{
            color: #333;
            padding: 8px 12px;
            background: white;
            border-radius: 4px;
            border: 1px solid #ddd;
        }}

        .my-prs-section {{
            background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%);
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
            border: 3px solid #4caf50;
        }}

        .copy-button {{
            background: #667eea;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.9em;
            margin-top: 10px;
            transition: background-color 0.2s ease;
        }}

        .copy-button:hover {{
            background: #5568d3;
        }}

        .copy-button:active {{
            background: #4556bb;
        }}

        .copy-button.copied {{
            background: #4caf50;
        }}

        .message-box {{
            background: white;
            border: 1px solid #ddd;
            border-radius: 4px;
            padding: 15px;
            margin: 10px 0;
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
            white-space: pre-wrap;
            line-height: 1.6;
        }}

        tbody tr.disabled {{
            opacity: 0.5;
            cursor: pointer;
        }}

        tbody tr.disabled:hover {{
            background-color: #f0f0f0;
        }}

        details {{
            background: #fafafa;
            border-radius: 8px;
            padding: 15px;
            margin: 20px 0;
            border: 1px solid #e0e0e0;
        }}

        summary {{
            cursor: pointer;
            font-weight: 600;
            font-size: 1.2em;
            color: #667eea;
            padding: 10px;
            margin: -15px;
            background: linear-gradient(135deg, #e8eaf6 0%, #d1d5f0 100%);
            border-radius: 8px;
            user-select: none;
        }}

        summary:hover {{
            background: linear-gradient(135deg, #d1d5f0 0%, #c5cae9 100%);
        }}

        details[open] summary {{
            border-radius: 8px 8px 0 0;
            margin: -15px -15px 20px -15px;
        }}

        .my-prs-summary {{
            font-size: 1.5em;
            padding: 15px;
            margin: -20px;
            background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%);
        }}

        details[open] .my-prs-summary {{
            margin: -20px -20px 20px -20px;
        }}

        .user-prs-summary {{
            font-size: 1.1em;
        }}

        details[open] .user-prs-summary {{
            margin-bottom: 10px;
        }}

        .user-pr-item {{
            padding: 10px;
            margin: 5px 0;
            background: #f0f0f0;
            border-radius: 4px;
            border-left: 4px solid #667eea;
        }}

        .user-pr-item:hover {{
            background: #e8e8e8;
        }}

        @media (max-width: 768px) {{
            .container {{
                padding: 20px;
            }}

            h1 {{
                font-size: 1.8em;
            }}

            h2 {{
                font-size: 1.4em;
            }}

            table {{
                font-size: 0.9em;
            }}

            th, td {{
                padding: 8px;
            }}

            .stats-grid {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>
    <script>
        const usersWithOpenPRs = {users_with_open_prs_json};
        const defaultSortBy = '{self.sort_by}';

        document.addEventListener('DOMContentLoaded', function() {{
            // Table sorting functionality
            const table = document.querySelector('table');
            if (table) {{
                const headers = table.querySelectorAll('th');
                const tbody = table.querySelector('tbody');

                // Set initial sort indicator
                const sortColumnMap = {{
                    'total_prs': 1,
                    'their_prs': 2,
                    'my_prs': 3,
                    'they_reviewed': 4,
                    'i_reviewed': 5,
                    'balance': 6,
                    'user': 0
                }};

                const defaultColumnIndex = sortColumnMap[defaultSortBy] || 1;
                const defaultHeader = headers[defaultColumnIndex];
                if (defaultHeader) {{
                    defaultHeader.classList.add('sort-desc');
                }}

                headers.forEach((header, index) => {{
                    header.addEventListener('click', () => {{
                        sortTable(index, header);
                    }});
                }});

                function sortTable(columnIndex, header) {{
                    const rows = Array.from(tbody.querySelectorAll('tr'));
                    const currentSort = header.classList.contains('sort-asc') ? 'asc' :
                                       header.classList.contains('sort-desc') ? 'desc' : 'none';

                    // Remove sort classes from all headers
                    headers.forEach(h => h.classList.remove('sort-asc', 'sort-desc'));

                    // Determine new sort direction
                    const newSort = currentSort === 'none' ? 'desc' :
                                   currentSort === 'desc' ? 'asc' : 'desc';

                    header.classList.add(newSort === 'asc' ? 'sort-asc' : 'sort-desc');

                    // Sort rows
                    rows.sort((a, b) => {{
                        const aValue = a.cells[columnIndex].textContent.trim();
                        const bValue = b.cells[columnIndex].textContent.trim();

                        // Try to parse as number (handle formats like "+1,234" or "-1,234")
                        const aNum = parseFloat(aValue.replace(/[+,]/g, ''));
                        const bNum = parseFloat(bValue.replace(/[+,]/g, ''));

                        if (!isNaN(aNum) && !isNaN(bNum)) {{
                            return newSort === 'asc' ? aNum - bNum : bNum - aNum;
                        }}

                        // String comparison
                        return newSort === 'asc' ?
                            aValue.localeCompare(bValue) :
                            bValue.localeCompare(aValue);
                    }});

                    // Re-append sorted rows
                    rows.forEach(row => tbody.appendChild(row));
                }}

                // Row click navigation - scroll to user section
                tbody.querySelectorAll('tr').forEach(row => {{
                    const username = row.cells[0].textContent.trim();

                    row.addEventListener('click', () => {{
                        const targetSection = document.getElementById('user-' + username);
                        if (targetSection) {{
                            targetSection.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
                        }}
                    }});
                }});
            }}

            // Handle back-to-table links with highlighting
            document.querySelectorAll('.back-to-table').forEach(link => {{
                link.addEventListener('click', (e) => {{
                    e.preventDefault();
                    const username = link.dataset.username;
                    const table = document.querySelector('table');

                    if (table) {{
                        table.scrollIntoView({{ behavior: 'smooth', block: 'start' }});

                        // Highlight the user's row
                        setTimeout(() => {{
                            const rows = table.querySelectorAll('tbody tr');
                            rows.forEach(row => {{
                                if (row.cells[0].textContent.trim() === username) {{
                                    row.classList.remove('highlight');
                                    // Force reflow to restart animation
                                    void row.offsetWidth;
                                    row.classList.add('highlight');

                                    // Remove highlight class after animation
                                    setTimeout(() => {{
                                        row.classList.remove('highlight');
                                    }}, 2000);
                                }}
                            }});
                        }}, 500);
                    }}
                }});
            }});

            // Copy to clipboard functionality
            document.querySelectorAll('.copy-button').forEach(button => {{
                button.addEventListener('click', function() {{
                    const messageBox = this.previousElementSibling;
                    if (messageBox && messageBox.classList.contains('message-box')) {{
                        const text = messageBox.textContent;
                        navigator.clipboard.writeText(text).then(() => {{
                            const originalText = this.textContent;
                            this.textContent = 'Copied!';
                            this.classList.add('copied');
                            setTimeout(() => {{
                                this.textContent = originalText;
                                this.classList.remove('copied');
                            }}, 2000);
                        }}).catch(err => {{
                            console.error('Failed to copy:', err);
                            alert('Failed to copy to clipboard');
                        }});
                    }}
                }});
            }});

            // PR copy button functionality
            document.querySelectorAll('.pr-copy-button').forEach(button => {{
                button.addEventListener('click', function(e) {{
                    e.stopPropagation();
                    const message = this.dataset.message;
                    if (message) {{
                        navigator.clipboard.writeText(message).then(() => {{
                            const originalText = this.textContent;
                            const originalBg = this.style.backgroundColor;
                            this.textContent = 'Copied!';
                            this.style.backgroundColor = '#4caf50';
                            setTimeout(() => {{
                                this.textContent = originalText;
                                this.style.backgroundColor = originalBg;
                            }}, 2000);
                        }}).catch(err => {{
                            console.error('Failed to copy:', err);
                            alert('Failed to copy to clipboard');
                        }});
                    }}
                }});
            }});
        }});
    </script>
</head>
<body>
    <div class="container">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 10px;">
            <div>
                <h1 style="margin: 0;">GitHub PR Review Analysis</h1>
                <div class="timestamp">Generated on {timestamp} for user: <strong>{self.username}</strong></div>
            </div>
            <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                <a href="https://github.com/florian-glombik/github-review-balance/issues" target="_blank" style="display: inline-flex; align-items: center; gap: 5px; padding: 6px 12px; background: #f0f0f0; color: #333; border: 1px solid #ccc; border-radius: 4px; text-decoration: none; font-size: 0.85em;"><svg height="16" width="16" viewBox="0 0 16 16" fill="currentColor"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/></svg>Report bugs</a>
                <a href="https://github.com/florian-glombik/github-review-balance" target="_blank" style="display: inline-flex; align-items: center; gap: 5px; padding: 6px 12px; background: #f0f0f0; color: #333; border: 1px solid #ccc; border-radius: 4px; text-decoration: none; font-size: 0.85em;"><svg height="16" width="16" viewBox="0 0 16 16" fill="currentColor"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/></svg>Improve this tool</a>
            </div>
        </div>
'''
