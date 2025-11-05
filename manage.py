#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
from dotenv import load_dotenv
from django.core.management import execute_from_command_line
load_dotenv()

def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm_saas.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", 'crm_saas.settings')

    # Check if DJANGO_PORT is set and append it only for runserver
    # Only append if no address:port is already provided
    if len(sys.argv) > 1 and sys.argv[1] == "runserver":
        # Check if address:port is already provided (sys.argv[2] would be the addrport)
        if len(sys.argv) == 2:  # Only "runserver" command, no address:port provided
            port = os.getenv('DJANGO_PORT')
            sys.argv.append(f"0.0.0.0:{port}")
        
    execute_from_command_line(sys.argv)