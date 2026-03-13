import base64
import json
import os
import shlex
import tempfile

import paramiko

from secrets_utils import get_secret


SSH_HOST = "ssh.liacs.nl"


def format_private_key(key_str: str) -> str:
    """Normalize private-key material loaded from Streamlit secrets."""
    normalized = key_str.replace("\\n", "\n").strip()
    header = "-----BEGIN OPENSSH PRIVATE KEY-----"
    footer = "-----END OPENSSH PRIVATE KEY-----"

    if normalized.startswith(header) and footer in normalized:
        key_body = normalized[len(header) : -len(footer)].strip()
        lines = [key_body[i : i + 70] for i in range(0, len(key_body), 70)]
        normalized = header + "\n" + "\n".join(lines) + "\n" + footer

    return normalized


def get_ssh_connection():
    """Establish an SSH connection using the LIACS SSH credentials."""
    ssh_username = get_secret("LIACS_SSH_USERNAME")
    if not ssh_username:
        raise ValueError(
            "LIACS_SSH_USERNAME is not defined in secrets. Please set it in your secrets file."
        )

    key_str = get_secret("LIACS_SSH_KEY")
    if not key_str:
        raise ValueError(
            "LIACS_SSH_KEY is not defined in secrets. Please set it in your secrets file."
        )

    normalized_key = format_private_key(key_str)
    with tempfile.NamedTemporaryFile(delete=False, mode="w") as tmp_key_file:
        tmp_key_file.write(normalized_key)
        tmp_key_path = tmp_key_file.name

    os.chmod(tmp_key_path, 0o600)

    try:
        try:
            key = paramiko.Ed25519Key.from_private_key_file(tmp_key_path)
        except paramiko.SSHException:
            key = paramiko.RSAKey.from_private_key_file(tmp_key_path)

        ssh = paramiko.SSHClient()
        ssh.load_system_host_keys()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(SSH_HOST, username=ssh_username, pkey=key)
        return ssh, tmp_key_path
    except Exception:
        os.remove(tmp_key_path)
        raise


def close_ssh_connection(ssh, tmp_key_path: str | None) -> None:
    """Close the SSH session and remove any temporary key file."""
    try:
        if ssh is not None:
            ssh.close()
    finally:
        if tmp_key_path and os.path.exists(tmp_key_path):
            os.remove(tmp_key_path)


def ensure_remote_directory(ssh, remote_directory: str) -> None:
    """Create a remote directory if it does not exist."""
    mkdir_cmd = f"mkdir -p {shlex.quote(remote_directory)}"
    _, stdout, stderr = ssh.exec_command(mkdir_cmd)
    exit_status = stdout.channel.recv_exit_status()
    err = stderr.read().decode().strip()
    if exit_status != 0 or err:
        raise PermissionError(
            f"Failed to create remote directory {remote_directory}: {err or exit_status}"
        )


def run_remote_python(ssh, python_code: str) -> str:
    """Execute Python code on the remote host and return stdout."""
    remote_cmd = f"python3 - <<'PY'\n{python_code}\nPY"
    _, stdout, stderr = ssh.exec_command(remote_cmd)
    exit_status = stdout.channel.recv_exit_status()
    output = stdout.read().decode().strip()
    error = stderr.read().decode().strip()
    if exit_status != 0:
        raise RuntimeError(error or f"Remote command failed with exit status {exit_status}.")
    if error:
        raise RuntimeError(error)
    return output


def run_remote_sql(ssh, db_path: str, sql_query: str, params=None, fetch: str | None = None):
    """Execute a parameterized SQLite query on the remote host."""
    payload = {
        "db_path": db_path,
        "sql_query": sql_query,
        "params": params or [],
        "fetch": fetch,
    }
    encoded_payload = base64.b64encode(json.dumps(payload).encode()).decode()
    python_code = f"""
import base64
import json
import sqlite3

payload = json.loads(base64.b64decode({encoded_payload!r}).decode())
conn = sqlite3.connect(payload["db_path"])
cursor = conn.cursor()
cursor.execute(payload["sql_query"], payload["params"])

if payload["fetch"] == "one":
    print(json.dumps(cursor.fetchone()))
elif payload["fetch"] == "all":
    print(json.dumps(cursor.fetchall()))

conn.commit()
conn.close()
"""
    output = run_remote_python(ssh, python_code.strip())
    if fetch:
        return json.loads(output) if output else None
    return None


def run_remote_sql_batch(ssh, db_path: str, operations: list[dict]):
    """Execute multiple SQLite operations in one remote Python process and transaction."""
    payload = {
        "db_path": db_path,
        "operations": operations,
    }
    encoded_payload = base64.b64encode(json.dumps(payload).encode()).decode()
    python_code = f"""
import base64
import json
import re
import sqlite3

payload = json.loads(base64.b64decode({encoded_payload!r}).decode())
conn = sqlite3.connect(payload["db_path"])
cursor = conn.cursor()
results = []

def validate_identifier(identifier, kind):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", identifier):
        raise ValueError(f"Invalid {{kind}} identifier: {{identifier!r}}")
    return identifier

for operation in payload["operations"]:
    op_type = operation["type"]

    if op_type == "execute":
        cursor.execute(operation["sql_query"], operation.get("params", []))
        fetch = operation.get("fetch")
        if fetch == "one":
            results.append(cursor.fetchone())
        elif fetch == "all":
            results.append(cursor.fetchall())
    elif op_type == "ensure_columns":
        table_name = validate_identifier(operation["table"], "table")
        cursor.execute(f"PRAGMA table_info({{table_name}})")
        existing_column_names = {{row[1] for row in cursor.fetchall()}}
        for column_name, column_type in operation["columns"].items():
            validate_identifier(column_name, "column")
            if column_name not in existing_column_names:
                cursor.execute(
                    f"ALTER TABLE {{table_name}} ADD COLUMN {{column_name}} {{column_type}}"
                )
    else:
        raise ValueError(f"Unsupported batch operation type: {{op_type!r}}")

conn.commit()
conn.close()

if results:
    print(json.dumps(results))
"""
    output = run_remote_python(ssh, python_code.strip())
    return json.loads(output) if output else []
