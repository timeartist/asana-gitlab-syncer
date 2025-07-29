import re
from typing import Optional, Tuple

import requests

from syncer.config import GITLAB_PAT, GITLAB_BASE_URL, GITLAB_API_BASE_URL

def construct_gitlab_comment_url(project_path: str, issue_id: str, comment_id: str) -> str:
    """Constructs a URL for a specific comment on a GitLab issue."""
    return f"{GITLAB_BASE_URL}/{project_path}/-/issues/{issue_id}#note_{comment_id}"

def parse_gitlab_issue_ref(issue_ref: str, url_encode=True) -> Optional[Tuple[str, str]]:
    """Parses a GitLab reference like 'project/path#123' into parts."""
    match = re.match(r'([^#]+)#(\d+)', issue_ref)
    if match:
        issue_id = match.group(2)
        
        if url_encode:
            project_path = match.group(1).replace('/', '%2F')
        else:
            project_path = match.group(1)
       
        return project_path, issue_id
    
    return None

def get_gitlab_issue_metadata(project_path: str, issue_id: str) -> dict:
    """Fetches high-level metadata for a specific GitLab issue."""
    url = f"{GITLAB_API_BASE_URL}/projects/{project_path}/issues/{issue_id}"
    headers = {"PRIVATE-TOKEN": GITLAB_PAT}

    response = requests.get(url, headers=headers)
    response.raise_for_status()

    return response.json()

def get_gitlab_issue_comments(project_path: str, issue_id: str) -> list:
    """Fetches all comments (notes) for a specific GitLab issue."""
    url = f"{GITLAB_API_BASE_URL}/projects/{project_path}/issues/{issue_id}/notes"
    headers = {"PRIVATE-TOKEN": GITLAB_PAT}
    params = {"sort": "asc", "order_by": "updated_at"}

    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()

    return response.json()

def fetch_data_for_gitlab_issues(issue_refs) -> dict:
    """Fetches metadata and comments for a list of GitLab issue references."""
    data = {}
    for issue_ref in issue_refs:
        parsed_ref = parse_gitlab_issue_ref(issue_ref)
        if not parsed_ref: 
            continue
        
        project_path, issue_id = parsed_ref
        print("project_path:", project_path, "issue_id:", issue_id)
        
        try:
            metadata = get_gitlab_issue_metadata(project_path, issue_id)
            comments = get_gitlab_issue_comments(project_path, issue_id)
            data[issue_ref] = {"metadata": metadata, "comments": comments}
            print(f"  -> Successfully fetched data for {issue_ref}")
            # pp(f"Metadata: {metadata}")
            # pp(f"Comments: {comments}")  
        except requests.exceptions.HTTPError as e:
            print(f"  -> FAILED to fetch data for {issue_ref}. Status: {e.response.status_code}")

    return data