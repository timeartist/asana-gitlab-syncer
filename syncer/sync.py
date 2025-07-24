from datetime import datetime
from typing import Optional

from syncer.config import *
from syncer.api import gitlab as GL, asana as A

def __format_gitlab_timestamp(timestamp: str) -> str:
    '''Format the timestamp to be human-readable with timezone'''
    try:
        dt = datetime.fromisoformat(timestamp)
        comment_timestamp = dt.astimezone().strftime('%a, %b %d, %Y at %-I:%M %p %Z')
    except (ValueError, TypeError):
        comment_timestamp = "Unknown Time"
    
    return comment_timestamp

def __format_gitlab_comment_for_asana(issue_ref: str, comment: dict) -> str:
    """Formats a GitLab comment for insertion into Asana."""
    parsed_ref = GL.parse_gitlab_issue_ref(issue_ref, url_encode=False)
    if not parsed_ref:
        print(f"ERROR: Could not parse GitLab issue reference: {issue_ref}")
        raise ValueError(f"Invalid GitLab issue reference: {issue_ref}")
    
    project_path, issue_id = parsed_ref
    comment_url = GL.construct_gitlab_comment_url(project_path, issue_id, comment['id'])
    comment_author = comment.get("author", {}).get("name", "Unknown User")

    if comment.get("updated_at"):
        comment_timestamp = __format_gitlab_timestamp(comment["updated_at"])

    return f'<body><a href="{comment_url}">[Comment {comment['id']}] From {comment_author} in GitLab on {comment_timestamp}:</a>\n\n<pre>{comment.get('body')}</pre></body>'

def _find_gitlab_task_in_subtasks(subtasks: list, gitlab_issue_ref: str, gitlab_field_gid: str) -> Optional[dict]:
    for st in subtasks:
        for field in st.get('custom_fields', []):
            if field['gid'] == gitlab_field_gid:
                gitlab_issues_string = field['display_value']
                issue_refs = [ref.strip() for ref in gitlab_issues_string.split(',')]

                if gitlab_issue_ref in issue_refs:
                    return st

    return None

def _update_existing_subtask(asana_subtask: dict, gitlab_issue: dict):
    print(f"  -> Found existing subtask: {asana_subtask['gid']}. Checking for new comments...")
    asana_comments = A.get_asana_existing_gitlab_comments(asana_subtask['gid'])
    gitlab_comments = dict((c['id'], c) for c in gitlab_issue['comments'] if not c.get('system'))
    for comment_id, comment in gitlab_comments.items():
        comment_body = __format_gitlab_comment_for_asana(gitlab_issue['metadata']['references']['full'], comment)
        if not asana_comments.get(comment_id):
            print(f"    -> Adding new comment {comment_id} to subtask {asana_subtask['gid']}")
            A.add_comment_to_asana_task(asana_subtask['gid'], comment_body)
        else:
            print(f"    -> Comment {comment_id} already exists in Asana subtask {asana_subtask['gid']}")
            # If the comment exists, we want to update it if it's different
            existing_comment_body = asana_comments[comment_id]['text']
            if existing_comment_body != comment_body:
                print(f"      -> Updating comment {comment_id} in Asana subtask {asana_subtask['gid']}")
                A.update_asana_comment(asana_comments[comment_id]['gid'], comment_body)

def _create_new_subtask(gitlab_issue:dict, parent_task_gid: str, gitlab_field_gid: str):
        meta = gitlab_issue['metadata']
        issue_ref = meta['references']['full']
        subtask_title = f"[GitLab Issue: {issue_ref}] {gitlab_issue['metadata'].get('title')}"
        # from pprint import pp; pp(meta)
        # import pdb; pdb.set_trace()
        subtask_description = (
            "<body>"
            f"This subtask is synced from GitLab.\n<b><u>Do not make changes in Asana, they will be overwritten</u></b>\n\n<hr>\n"
            f"<b>GitLab URL:</b><a href=\"{meta.get('web_url')}\">{meta.get('web_url')}</a>\n"
            f"<b>Author:</b> {meta.get('author', {}).get('name')}\n"
            f"<b>Created at:</b> {__format_gitlab_timestamp(meta.get('created_at'))}\n"
            f"<b>Description:</b>\n<pre>{meta.get('description', 'No description provided')}</pre>"
            "</body>"
        )
        new_subtask = A.create_asana_subtask(parent_task_gid, subtask_title, subtask_description, issue_ref, gitlab_field_gid)
        print(f"    -> Created new subtask: {new_subtask['gid']}")
        
        for comment in gitlab_issue['comments']:
            if not comment.get('system'):
                print(f"      -> Adding comment {comment['id']} to new subtask {new_subtask['gid']}") 
                comment_body = __format_gitlab_comment_for_asana(issue_ref, comment)
                A.add_comment_to_asana_task(new_subtask['gid'], comment_body)
        
        return new_subtask


def sync_gitlab_to_asana(gitlab_data: dict, gitlab_to_asana_map: dict, gitlab_field_gid: str):
    for issue_ref, issue_data in gitlab_data.items():
        ##take our parent issues, and find an existing generated gitlab if it exists
        ##if it does, add/update comments for it
        ##if it doesn't, create a new subtask with all comments
        parent_issues = gitlab_to_asana_map.get(issue_ref, [])
        for url in parent_issues:
            parent_task_gid = url.strip('/').split('/')[-1]
            print(f"\nProcessing Asana task: {parent_task_gid} for GitLab issue: {issue_ref}")

            # Check for existing subtask
            existing_subtasks = A.get_asana_subtasks(parent_task_gid)
            print(f"  -> Found {len(existing_subtasks)} existing subtasks for parent task {parent_task_gid}.")
            
            target_subtask = _find_gitlab_task_in_subtasks(existing_subtasks, issue_ref, gitlab_field_gid)
            if target_subtask:
                _update_existing_subtask(target_subtask, issue_data)
            else:
                print(f"  -> No existing subtask found. Creating a new one...")
                target_subtask = _create_new_subtask(issue_data, parent_task_gid, gitlab_field_gid)
            # Check if GitLab issue is closed but Asana subtask is open
        
            gitlab_closed = issue_data['metadata']['state'] == 'closed'
            asana_completed = target_subtask['completed']
            print(f"  -> GitLab issue is {'closed' if gitlab_closed else 'open'}, Asana subtask is {'completed' if asana_completed else 'open'}.")
            
            if gitlab_closed and not asana_completed:
                print(f"    -> GitLab issue is closed, but Asana subtask is open. Closing Asana subtask {target_subtask['gid']}...")
                A.update_task_status(target_subtask['gid'], True)
            elif not gitlab_closed and asana_completed:
                print(f"    -> GitLab issue is open, but Asana subtask is completed. Reopening Asana subtask {target_subtask['gid']}...")
                A.update_task_status(target_subtask['gid'], False)

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


def main():
    # print(f'ASANA_WORKSPACE_NAME: {ASANA_WORKSPACE_NAME}')
    # print(f'ASANA_GITLAB_FIELD: {ASANA_GITLAB_FIELD}')
    # print(f'ASANA_PAT: {ASANA_PAT}')
    # print(f'ASANA_API_BASE_URL: {ASANA_API_BASE_URL}')
    # print(f'GITLAB_PAT: {GITLAB_PAT}')
    # print(f'GITLAB_BASE_URL: {GITLAB_BASE_URL}')
    # print(f'GITLAB_API_BASE_URL: {GITLAB_API_BASE_URL}')
    
    # Find relevant Asana tasks
    workspace_gid = A.get_workspace_gid(ASANA_WORKSPACE_NAME)
    gitlab_field_gid = A.get_custom_field_gid(workspace_gid, ASANA_GITLAB_FIELD)
    found_tasks = A.find_tasks_with_populated_field(workspace_gid, gitlab_field_gid)
    
    ## map to gitlab issues
    gitlab_to_asana_map = transform_and_filter_asana_tasks_to_gitlab_map(found_tasks, gitlab_field_gid)
    print(f"Filtered to {len(gitlab_to_asana_map)} GitLab issue references in Asana tasks.")
        
    # Fetch data from GitLab for the issues we found
    gitlab_data = GL.fetch_data_for_gitlab_issues(gitlab_to_asana_map.keys())

    print("\n--- Syncing GitLab data to Asana subtasks ---")
    sync_gitlab_to_asana(gitlab_data, gitlab_to_asana_map, gitlab_field_gid)
    
if __name__ == "__main__":
    main()