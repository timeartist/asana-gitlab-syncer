import re
from os import getenv
from pprint import pp
from typing import Optional, Tuple


import requests

ASANA_PAT = getenv("ASANA_PAT")
ASANA_WORKSPACE_NAME = getenv("ASANA_WORKSPACE_NAME", '')
ASANA_GITLAB_FIELD = getenv("ASANA_GITLAB_FIELD", "Gitlab Issues")
ASANA_API_BASE_URL = "https://app.asana.com/api/1.0"

GITLAB_PAT = getenv("GITLAB_PAT")
GITLAB_BASE_URL = getenv("GITLAB_BASE_URL") or 'https://gitlab.com'
GITLAB_API_BASE_URL = f"{GITLAB_BASE_URL}/api/v4"

###########
## ASANA ##
###########


def get_asana_subtasks(parent_task_gid: str) -> list:
    """Fetches all subtasks for a given parent Asana task."""
    url = f"{ASANA_API_BASE_URL}/tasks/{parent_task_gid}/subtasks"
    headers = {"Authorization": f"Bearer {ASANA_PAT}", "Accept": "application/json"}
    params = {"opt_fields": "name,notes,custom_fields"}

    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    # pp(response.json())

    return response.json().get('data', [])

def add_comment_to_asana_task(task_gid: str, comment_body: str):
    """Adds a new comment (story) to an Asana task."""
    url = f"{ASANA_API_BASE_URL}/tasks/{task_gid}/stories"
    headers = {"Authorization": f"Bearer {ASANA_PAT}", "Accept": "application/json"}
    payload = {"data": {"text": comment_body}}

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()

def create_asana_subtask(parent_task_gid: str, name: str, notes: str, gitlab_ref: str, gitlab_field_gid: str) -> dict:
    """Creates a new subtask under a parent task and sets the GitLab custom field."""
    url = f"{ASANA_API_BASE_URL}/tasks/{parent_task_gid}/subtasks"
    headers = {"Authorization": f"Bearer {ASANA_PAT}", "Accept": "application/json"}
    payload = {
        "data": {
            "name": name,
            "notes": notes,
            "custom_fields": {
                gitlab_field_gid: gitlab_ref
            }
        }
    }

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json().get('data')

def get_asana_task_comments(task_gid: str) -> list:
    """Fetches all comments (stories) for a given Asana task."""
    url = f"{ASANA_API_BASE_URL}/tasks/{task_gid}/stories"
    headers = {"Authorization": f"Bearer {ASANA_PAT}", "Accept": "application/json"}

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    # Filter for actual user comments, not system-generated stories
    return [story['text'] for story in response.json().get('data', []) if story.get('type') == 'comment']

def get_workspace_gid(workspace_name: str) -> str:
    """Finds the GID of a workspace by its name."""
    print(f"Searching for Asana workspace named '{workspace_name}'...")
    url = f"{ASANA_API_BASE_URL}/workspaces"

    headers = {"Authorization": f"Bearer {ASANA_PAT}", "Accept": "application/json"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    
    workspaces = response.json()['data']
    for workspace in workspaces:
        if workspace['name'] == workspace_name:
            print(f"Found Asana workspace GID: {workspace['gid']}")
            return workspace['gid']
    
    raise ValueError(f"Workspace '{workspace_name}' not found.")

def get_custom_field_gid(workspace_gid: str, field_name: str) -> str:
    """Finds the GID of a custom field within a workspace by its name."""
    print(f"Searching for Asana custom field '{field_name}'...")

    url = f"{ASANA_API_BASE_URL}/workspaces/{workspace_gid}/custom_fields"
    headers = {"Authorization": f"Bearer {ASANA_PAT}", "Accept": "application/json"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()

    custom_fields = response.json()['data']
    for field in custom_fields:
        if field['name'] == field_name:
            print(f"Found Asana custom field GID: {field['gid']}")
            return field['gid']
    
    raise ValueError(f"Custom field '{field_name}' not found.")

def find_tasks_with_populated_field(workspace_gid: str, custom_field_gid: str) -> list:
    """Searches for all open tasks in a workspace where a specific custom field is set."""
    print("Searching Asana for open tasks with the populated custom field...")

    
    url = f"{ASANA_API_BASE_URL}/workspaces/{workspace_gid}/tasks/search"
    headers = {"Authorization": f"Bearer {ASANA_PAT}", "Accept": "application/json"}
    params = {
        f"custom_fields.{custom_field_gid}.is_set": "true",
        "completed": "false",  # Only open (incomplete) tasks
        "opt_fields": "name,permalink_url,custom_fields"
    }
    
    all_tasks = []
    ##TODO: this makes me nervous, but there's not an obvious better way
    while True:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        result_data = response.json()
        tasks = result_data.get('data', [])
        all_tasks.extend(tasks)
        if result_data.get('next_page'):
            print(f"  ...fetched {len(all_tasks)} Asana tasks, getting next page...")
            params['offset'] = result_data['next_page']['offset']
        else:
            break
    
    print(f"Asana search complete. Found {len(all_tasks)} total open tasks.")
    return all_tasks

def transform_and_filter_asana_tasks_to_gitlab_map(tasks: list, gitlab_field_gid: str) -> dict:
    """Transforms Asana tasks into a map of GitLab issue references to Asana task URLs."""
    gitlab_to_asana_map = {}

    ## this looks a lot worse than it is, the custom field array is always relatively small, as should be the number of gitlab issues
    for task in tasks:
        print(f"Processing Asana task: {task['gid']} | {task['name']}")
        if not task['name'].startswith('[GitLab Issue'):
            for field in task.get('custom_fields', []):
                if field['gid'] == gitlab_field_gid and field.get('display_value'):
                    gitlab_issues_string = field['display_value']
                    for issue_ref in gitlab_issues_string.split(','):
                        clean_issue_ref = issue_ref.strip()
                        if clean_issue_ref:
                            if clean_issue_ref not in gitlab_to_asana_map:
                                gitlab_to_asana_map[clean_issue_ref] = []
                            gitlab_to_asana_map[clean_issue_ref].append(task['permalink_url'])
                    break

    return gitlab_to_asana_map

############
## GITLAB ##
############


def parse_gitlab_issue_ref(issue_ref: str) -> Optional[Tuple[str, str]]:
    """Parses a GitLab reference like 'project/path#123' into parts."""
    match = re.match(r'([^#]+)#(\d+)', issue_ref)
    if match:
        project_path = match.group(1).replace('/', '%2F')
        issue_id = match.group(2)
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

if __name__ == "__main__":
    
    # ---------------------------------------------

    # if not ASANA_PAT or not GITLAB_PAT:
    if not ASANA_PAT:
        print("ERROR: ASANA_PAT environment variable is not set.")
        exit(1)
        # print("ERROR: ASANA_PAT and/or GITLAB_PAT environment variables are not set.")

    # Find Asana tasks and build the initial map
    workspace_gid = get_workspace_gid(ASANA_WORKSPACE_NAME)
    gitlab_field_gid = get_custom_field_gid(workspace_gid, ASANA_GITLAB_FIELD)
    found_tasks = find_tasks_with_populated_field(workspace_gid, gitlab_field_gid)
    gitlab_to_asana_map = transform_and_filter_asana_tasks_to_gitlab_map(found_tasks, gitlab_field_gid)
    print(gitlab_to_asana_map)
        
    # Fetch data from GitLab
    all_gitlab_data = {}
    for issue_ref in gitlab_to_asana_map.keys():
        parsed_ref = parse_gitlab_issue_ref(issue_ref)
        if not parsed_ref: 
            continue
        project_path, issue_id = parsed_ref
        print("project_path:", project_path, "issue_id:", issue_id)
        try:
            metadata = get_gitlab_issue_metadata(project_path, issue_id)
            comments = get_gitlab_issue_comments(project_path, issue_id)
            all_gitlab_data[issue_ref] = {"metadata": metadata, "comments": comments}
            print(f"  -> Successfully fetched data for {issue_ref}")
            # pp(f"Metadata: {metadata}")
            # pp(f"Comments: {comments}")
        except requests.exceptions.HTTPError as e:
            print(f"  -> FAILED to fetch data for {issue_ref}. Status: {e.response.status_code}")


        # Sync GitLab data to Asana subtasks
        print("\n--- Syncing GitLab data to Asana subtasks ---")
        for issue_ref, gitlab_data in all_gitlab_data.items():
            asana_urls = gitlab_to_asana_map.get(issue_ref, [])
            for asana_url in asana_urls:
                parent_task_gid = asana_url.strip('/').split('/')[-1]
                print(f"\nProcessing Asana task: {parent_task_gid} for GitLab issue: {issue_ref}")

                # Check for existing subtask
                existing_subtasks = get_asana_subtasks(parent_task_gid)
                print(f"  -> Found {len(existing_subtasks)} existing subtasks for parent task {parent_task_gid}.")
                
                target_subtask = None
                for st in existing_subtasks:
                    for field in st.get('custom_fields', []):
                        if field['gid'] == gitlab_field_gid:
                            gitlab_issues_string = field['display_value']
                            issue_refs = [ref.strip() for ref in gitlab_issues_string.split(',')]
                            
                            if issue_ref in issue_refs:
                                target_subtask = st
                                break
                    
                    if target_subtask:
                        break

                if target_subtask:
                    print(f"  -> Found existing subtask: {target_subtask['gid']}. Checking for new comments...")
                    # UPDATE: Only add new comments
                    existing_comments = get_asana_task_comments(target_subtask['gid'])
                    new_gitlab_comments = [c for c in gitlab_data['comments'] if not c.get('system')]
                    
                    for comment in new_gitlab_comments:
                        comment_author = comment.get("author", {}).get("name", "Unknown User")
                        comment_body = f"From {comment_author} in GitLab:\n\n{comment.get('body')}"
                        if comment_body not in existing_comments:
                            print(f"    -> Adding new comment from {comment_author}")
                            print(comment_body)
                            add_comment_to_asana_task(target_subtask['gid'], comment_body)

                else:
                    print(f"  -> No existing subtask found. Creating a new one...")
                    # CREATE: Make new subtask and add all comments
                    meta = gitlab_data['metadata']
                    subtask_title = f"[GitLab Issue: {issue_ref}] {gitlab_data['metadata'].get('title')}"
                    subtask_description = (
                        f"This subtask is synced from GitLab.\n\n"
                        f"GitLab URL: {meta.get('web_url')}\n"
                        f"State: {meta.get('state')}\n"
                        f"Author: {meta.get('author', {}).get('name')}"
                    )
                    new_subtask = create_asana_subtask(parent_task_gid, subtask_title, subtask_description, issue_ref, gitlab_field_gid)
                    print(f"    -> Created new subtask: {new_subtask['gid']}")
                    
                    for comment in gitlab_data['comments']:
                        if not comment.get('system'):
                            comment_author = comment.get("author", {}).get("name", "Unknown User")
                            comment_body = f"From {comment_author} in GitLab:\n\n{comment.get('body')}"
                            print(f"    -> Adding comment from {comment_author}")
                            print(comment_body)
                            add_comment_to_asana_task(new_subtask['gid'], comment_body)