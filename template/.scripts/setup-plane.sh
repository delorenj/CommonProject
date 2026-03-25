#!/usr/bin/env python3
"""Creates a Plane project in the 33god workspace and writes .plane.json"""
import json
import os
import re
import sys
import urllib.request
import urllib.error

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(SCRIPT_DIR, "project-data.json")
PLANE_API = "https://plane.delo.sh/api/v1"
WORKSPACE = "33god"


def write_plane_json(workspace, project_id, identifier):
    with open(".plane.json", "w") as f:
        json.dump(
            {"workspace": workspace, "project_id": project_id, "project_identifier": identifier},
            f,
            indent=2,
        )
        f.write("\n")


def main():
    with open(DATA_FILE) as f:
        data = json.load(f)

    name = data["project_name"]
    desc = data.get("project_description", "")

    # Derive identifier: first 4 alphanumeric chars, uppercased
    identifier = re.sub(r"[^A-Za-z0-9]", "", name)[:4].upper()
    if len(identifier) < 2:
        identifier += "XX"

    api_key = os.environ.get("PLANE_33GOD_API_KEY", "")
    if not api_key:
        print("WARNING: PLANE_33GOD_API_KEY not set. Writing placeholder .plane.json")
        print("  Set the key and re-run: python3 .scripts/setup-plane.sh")
        write_plane_json(WORKSPACE, "PLACEHOLDER", identifier)
        return

    payload = json.dumps({"name": name, "description": desc, "identifier": identifier, "network": 2}).encode()

    req = urllib.request.Request(
        f"{PLANE_API}/workspaces/{WORKSPACE}/projects/",
        data=payload,
        headers={"X-API-Key": api_key, "Content-Type": "application/json", "User-Agent": "CommonProject/1.0", "Accept": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read())
            project_id = body.get("id", "PLACEHOLDER")
            actual_ident = body.get("identifier", identifier)
            write_plane_json(WORKSPACE, project_id, actual_ident)
            print(f"Plane project created: {actual_ident} ({project_id})")
    except urllib.error.HTTPError as e:
        print(f"WARNING: Plane API returned {e.code}. Writing placeholder .plane.json")
        try:
            print(f"  Response: {e.read().decode()}")
        except Exception:
            pass
        write_plane_json(WORKSPACE, "PLACEHOLDER", identifier)
    except Exception as e:
        print(f"WARNING: Plane API request failed: {e}. Writing placeholder .plane.json")
        write_plane_json(WORKSPACE, "PLACEHOLDER", identifier)


if __name__ == "__main__":
    main()
