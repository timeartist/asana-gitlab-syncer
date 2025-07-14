from os import getenv
from pprint import pp

import requests

ASANA_PAT = getenv("ASANA_PAT")
ASANA_WORKSPACE_NAME = getenv("ASANA_WORKSPACE_NAME", '')
ASANA_GITLAB_FIELD = getenv("ASANA_GITLAB_FIELD", "Gitlab Issues")
ASANA_API_BASE_URL = "https://app.asana.com/api/1.0"

GITLAB_BASE_URL = getenv("GITLAB_BASE_URL") or 'https://gitlab.com'
GITLAB_API_BASE_URL = f"{GITLAB_BASE_URL}/api/v4"


# --- Asana Helper Functions ---

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
    all_tasks = []
    url = f"{ASANA_API_BASE_URL}/workspaces/{workspace_gid}/tasks/search"
    headers = {"Authorization": f"Bearer {ASANA_PAT}", "Accept": "application/json"}
    params = {
        f"custom_fields.{custom_field_gid}.is_set": "true",
        "completed": "false",  # Only open (incomplete) tasks
        "opt_fields": "name,permalink_url,custom_fields"
    }
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

\
if __name__ == "__main__":
    
    # ---------------------------------------------

    # if not ASANA_PAT or not GITLAB_PAT:
    if not ASANA_PAT:
        print("ERROR: ASANA_PAT environment variable is not set.")
        exit(1)
        # print("ERROR: ASANA_PAT and/or GITLAB_PAT environment variables are not set.")
    else:
        # Find Asana tasks and build the initial map
        workspace_gid = get_workspace_gid(ASANA_WORKSPACE_NAME)
        gitlab_field_gid = get_custom_field_gid(workspace_gid, ASANA_GITLAB_FIELD)
        found_tasks = find_tasks_with_populated_field(workspace_gid, gitlab_field_gid)
        pp(found_tasks)
        
        # gitlab_to_asana_map = {}
        # for task in found_tasks:
        #     for field in task.get('custom_fields', []):
        #         if field['gid'] == gitlab_field_gid and field.get('display_value'):
        #             gitlab_issues_string = field['display_value']
        #             for issue_ref in gitlab_issues_string.split(','):
        #                 clean_issue_ref = issue_ref.strip()
        #                 if clean_issue_ref:
        #                     if clean_issue_ref not in gitlab_to_asana_map:
        #                         gitlab_to_asana_map[clean_issue_ref] = []
        #                     gitlab_to_asana_map[clean_issue_ref].append(task['permalink_url'])
        #             break
        