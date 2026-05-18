"""
SSH utility functions for connecting to remote servers and managing SSH keys.
Consolidates all SSH-related functionality in one place.
"""

import os
import tempfile
import streamlit as st
import paramiko


def format_private_key(key_str):
    """
    Normalize the private key string for proper formatting.
    
    Handles newline characters and wraps OpenSSH private keys to 70 characters per line
    as required by the OpenSSH format specification.
    
    Args:
        key_str: The private key string to format
        
    Returns:
        Properly formatted private key string
    """
    # Replace escaped newlines with actual newlines
    if "\\n" in key_str:
        key_str = key_str.replace("\\n", "\n")
    
    # Format OpenSSH private keys with proper line wrapping
    if key_str.startswith("-----BEGIN OPENSSH PRIVATE KEY-----") and "-----END OPENSSH PRIVATE KEY-----" in key_str:
        header = "-----BEGIN OPENSSH PRIVATE KEY-----"
        footer = "-----END OPENSSH PRIVATE KEY-----"
        key_body = key_str[len(header):-len(footer)].strip()
        # Wrap to 70 characters per line
        lines = [key_body[i:i + 70] for i in range(0, len(key_body), 70)]
        key_str = header + "\n" + "\n".join(lines) + "\n" + footer
    
    return key_str


def get_ssh_connection():
    """
    Establish an SSH connection using the LIACS SSH credentials from Streamlit secrets.
    
    Reads SSH credentials from st.secrets, formats the private key, and establishes
    a connection to ssh.liacs.nl. Supports both Ed25519 and RSA keys.
    
    Returns:
        tuple: (ssh_client, tmp_key_path) where ssh_client is the connected paramiko 
               SSHClient and tmp_key_path is the path to the temporary key file that
               should be deleted after use.
               
    Raises:
        ValueError: If required credentials are not found in secrets
        Exception: If connection fails or key cannot be loaded
        
    Example:
        ssh, tmp_key_path = get_ssh_connection()
        try:
            # Use SSH connection
            stdin, stdout, stderr = ssh.exec_command('ls')
        finally:
            ssh.close()
            os.remove(tmp_key_path)
    """
    ssh_host = "ssh.liacs.nl"
    ssh_username = st.secrets.get("LIACS_SSH_USERNAME")
    if not ssh_username:
        raise ValueError("LIACS_SSH_USERNAME is not defined in secrets. Please set it in your secrets file.")

    key_str = st.secrets.get("LIACS_SSH_KEY")
    if not key_str:
        raise ValueError("LIACS_SSH_KEY is not defined in secrets. Please set it in your secrets file.")
    
    key_str = format_private_key(key_str)

    # Write key to temporary file
    with tempfile.NamedTemporaryFile(delete=False, mode="w") as tmp_key_file:
        tmp_key_file.write(key_str)
        tmp_key_path = tmp_key_file.name

    try:
        # Try Ed25519 key first, fall back to RSA
        try:
            key = paramiko.Ed25519Key.from_private_key_file(tmp_key_path)
        except paramiko.SSHException:
            key = paramiko.RSAKey.from_private_key_file(tmp_key_path)
        
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(ssh_host, username=ssh_username, pkey=key)
        return ssh, tmp_key_path
    except Exception as e:
        # Clean up temp file on failure
        os.remove(tmp_key_path)
        raise e


def ensure_remote_directory(ssh, remote_directory):
    """
    Ensures the remote directory exists by executing a mkdir command via SSH.
    
    Args:
        ssh: Active paramiko SSHClient connection
        remote_directory: Path to the directory to create on the remote server
        
    Raises:
        PermissionError: If the directory cannot be created due to permissions
    """
    mkdir_cmd = f"mkdir -p {remote_directory}"
    stdin, stdout, stderr = ssh.exec_command(mkdir_cmd)
    err = stderr.read().decode().strip()
    if err:
        raise PermissionError(f"Failed to create remote directory {remote_directory}: {err}")

