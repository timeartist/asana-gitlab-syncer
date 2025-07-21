from os import getenv

ASANA_PAT = getenv("ASANA_PAT")
ASANA_WORKSPACE_NAME = getenv("ASANA_WORKSPACE_NAME", '')
ASANA_GITLAB_FIELD = getenv("ASANA_GITLAB_FIELD", "Gitlab Issues")
ASANA_API_BASE_URL = "https://app.asana.com/api/1.0"

GITLAB_PAT = getenv("GITLAB_PAT")
GITLAB_BASE_URL = getenv("GITLAB_BASE_URL") or 'https://gitlab.com'
GITLAB_API_BASE_URL = f"{GITLAB_BASE_URL}/api/v4"