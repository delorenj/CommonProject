"""Provider binding render contract without live ticket services (PJAN-17)."""
import json
from pathlib import Path

from jinja2 import Environment
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("provider", "board_id", "expected_url", "workspace"),
    [
        ("plane", "plane-project-id", "https://plane.delo.sh/33god/projects/plane-project-id/issues/", "33god"),
        ("trello", "trello-board-id", "https://trello.com/b/trello-board-id", ""),
        ("trello", "", "", ""),
    ],
)
def test_binding_renders_provider_url(provider: str, board_id: str, expected_url: str, workspace: str) -> None:
    text = (ROOT / "template/.project.json.jinja").read_text()
    rendered = Environment().from_string(text).render(
        project_name="Disposable", project_description="fixture", project_slug="disposable",
        ticket_provider=provider, plane_workspace="33god", plane_project_id=board_id,
        plane_base="https://plane.delo.sh", project_identifier="DISP",
    )
    binding = json.loads(rendered)["ticket_provider"]
    assert binding == {
        "type": provider, "workspace": workspace, "identifier": "DISP",
        "board_id": board_id, "board_url": expected_url,
    }


def test_choices_exclude_linear() -> None:
    choices = yaml.safe_load((ROOT / "copier.yml").read_text())["ticket_provider"]["choices"]
    assert choices == {"Plane": "plane", "Trello": "trello"}


def test_generated_agent_guidance_is_provider_neutral() -> None:
    text = (ROOT / "template/AGENTS.md.jinja").read_text()
    rendered = Environment().from_string(text).render(
        project_name="Disposable", project_description="fixture", is_obsidian_plugin=False,
    )
    assert ".project.json" in rendered
    assert "`plane` and `trello`" in rendered
    assert "must not be interpreted as Plane" in rendered
