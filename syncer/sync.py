from typing import Optional

from syncer.config import ASANA_PAT, ASANA_WORKSPACE_NAME, ASANA_GITLAB_FIELD
from syncer.api import gitlab as GL, asana as A

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
        comment_body = GL.format_gitlab_comment_for_asana(gitlab_issue['metadata']['references']['full'], comment)
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
        subtask_description = (
            f"This subtask is synced from GitLab.\n\n"
            f"GitLab URL: {meta.get('web_url')}\n"
            f"Author: {meta.get('author', {}).get('name')}"
        )
        new_subtask = A.create_asana_subtask(parent_task_gid, subtask_title, subtask_description, issue_ref, gitlab_field_gid)
        print(f"    -> Created new subtask: {new_subtask['gid']}")
        
        for comment in gitlab_issue['comments']:
            if not comment.get('system'):
                print(f"      -> Adding comment {comment['id']} to new subtask {new_subtask['gid']}") 
                comment_body = GL.format_gitlab_comment_for_asana(issue_ref, comment)
                A.add_comment_to_asana_task(new_subtask['gid'], comment_body)


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
                _create_new_subtask(issue_data, parent_task_gid, gitlab_field_gid)


def main():
    # if not ASANA_PAT or not GITLAB_PAT:
    if not ASANA_PAT:
        print("ERROR: ASANA_PAT environment variable is not set.")
        exit(1)
        # print("ERROR: ASANA_PAT and/or GITLAB_PAT environment variables are not set.")

    # Find Asana tasks and build the initial map
    workspace_gid = A.get_workspace_gid(ASANA_WORKSPACE_NAME)
    gitlab_field_gid = A.get_custom_field_gid(workspace_gid, ASANA_GITLAB_FIELD)
    found_tasks = A.find_tasks_with_populated_field(workspace_gid, gitlab_field_gid)
    gitlab_to_asana_map = A.transform_and_filter_asana_tasks_to_gitlab_map(found_tasks, gitlab_field_gid)
    print(f"Filtered to {len(gitlab_to_asana_map)} GitLab issue references in Asana tasks.")
        
    # Fetch data from GitLab for the issues we found
    gitlab_data = GL.fetch_data_for_gitlab_issues(gitlab_to_asana_map.keys())

    print("\n--- Syncing GitLab data to Asana subtasks ---")
    sync_gitlab_to_asana(gitlab_data, gitlab_to_asana_map, gitlab_field_gid)
    
if __name__ == "__main__":
    main()