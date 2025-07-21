import re

import requests

from syncer.config import ASANA_PAT, ASANA_API_BASE_URL

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

def update_asana_comment(story_gid: str, updated_text: str) -> dict:
    """Updates an existing comment (story) on an Asana task."""
    url = f"{ASANA_API_BASE_URL}/stories/{story_gid}"
    headers = {"Authorization": f"Bearer {ASANA_PAT}", "Accept": "application/json"}
    payload = {"data": {"text": updated_text}}

    response = requests.put(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json().get('data')

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

def get_asana_existing_gitlab_comments(task_gid: str) -> dict:
    """Fetches all comments (stories) for a given Asana task."""
    url = f"{ASANA_API_BASE_URL}/tasks/{task_gid}/stories"
    headers = {"Authorization": f"Bearer {ASANA_PAT}", "Accept": "application/json"}

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    # Filter for comments that we made, which start with "Comment <id>"
    comments = {}
    for story in response.json().get('data', []):

        if story.get('type') == 'comment':
            text = story.get('text', '')
            match = re.match(r'^Comment (\d+)', text)
            if match:
                comment_id = match.group(1)
                comments[int(comment_id)] = {'gid': story['gid'], 'text': text}

    return comments

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