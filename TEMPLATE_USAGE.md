# Template Usage Guide

## Installation

```bash
# Install copier globally
uv tool install copier

# Or with pip
pip install copier
```

## Creating a New Project

### Interactive Mode

```bash
copier copy /path/to/CommonProject my-awesome-project
```

Follow the prompts to configure your project.

### Non-Interactive Mode

```bash
copier copy /path/to/CommonProject my-awesome-project \
  --data project_name="My Awesome Project" \
  --data project_type=software \
  --data primary_language=python \
  --data plane_workspace=33god \
  --data plane_project_id=YOUR_PROJECT_ID \
  --data project_identifier=MAW \
  --data uses_docker=true \
  --data uses_event_bus=true
```

## Common Scenarios

### Hardware IoT Device

```bash
copier copy /path/to/CommonProject my-iot-device \
  --data project_name="My IoT Device" \
  --data project_type=hardware \
  --data has_hardware=true \
  --data hardware_platform="Raspberry Pi Zero 2 W" \
  --data hardware_hostname="mydevice.local" \
  --data hardware_peripherals="Camera Module, Temperature Sensor" \
  --data has_agent=true \
  --data agent_name="DeviceBot" \
  --data agent_role="Device Controller" \
  --data primary_language=python
```

### Microservice API

```bash
copier copy /path/to/CommonProject my-api-service \
  --data project_name="My API Service" \
  --data project_type=software \
  --data primary_language=python \
  --data uses_docker=true \
  --data uses_event_bus=true \
  --data additional_services="postgres,redis"
```

### React Dashboard

```bash
copier copy /path/to/CommonProject my-dashboard \
  --data project_name="My Dashboard" \
  --data project_type=dashboard \
  --data primary_language=typescript \
  --data uses_docker=true \
  --data uses_event_bus=true
```

### CLI Tool

```bash
copier copy /path/to/CommonProject my-cli-tool \
  --data project_name="My CLI Tool" \
  --data project_type=tooling \
  --data primary_language=rust \
  --data uses_docker=false \
  --data uses_event_bus=false
```

## Template Variables Reference

| Variable               | Type   | Description                         | Default        |
| ---------------------- | ------ | ----------------------------------- | -------------- |
| `project_name`         | str    | Display name                        | Required       |
| `project_slug`         | str    | Directory/package name              | Auto-generated |
| `project_description`  | str    | One-line description                | ""             |
| `project_type`         | choice | software/hardware/dashboard/tooling | software       |
| `has_hardware`         | bool   | Physical hardware integration       | false          |
| `hardware_platform`    | str    | Hardware description                | ""             |
| `hardware_hostname`    | str    | SSH hostname                        | {slug}.local   |
| `hardware_peripherals` | str    | Comma-separated list                | ""             |
| `has_agent`            | bool   | Has AI agent                        | true           |
| `agent_name`           | str    | Agent display name                  | {project_name} |
| `agent_role`           | str    | Agent purpose                       | ""             |
| `plane_workspace`      | str    | Plane workspace                     | 33god          |
| `plane_project_id`     | str    | Plane project ID                    | Required       |
| `project_identifier`   | str    | Ticket prefix (2+ chars)            | Required       |
| `primary_language`     | choice | python/typescript/rust              | python         |
| `uses_docker`          | bool   | Enable Docker                       | true           |
| `uses_event_bus`       | bool   | Bloodbank integration               | true           |
| `additional_services`  | str    | Extra services (comma-sep)          | ""             |
| `git_remote_url`       | str    | Git remote URL                      | ""             |
| `initialize_god_docs`  | bool   | Create GOD docs                     | true           |
| `component_domain`     | choice | 33GOD domain                        | custom         |

## Post-Generation Checklist

After generating a project:

- [ ] Review and customize generated files
- [ ] Copy `project.env.example` to `.env` and fill in values
- [ ] Run `mise trust` to enable environment loading
- [ ] Initialize git repository: `git init`
- [ ] Initialize gh repository: `gh repo create`
- [ ] Create Plane ticket and move to "In Progress"
- [ ] Initialize main trunk: `git add -A && git commit -m "Initial commit" && git push -u origin main`
- [ ] Test development workflow: `mise run dev`
- [ ] If using Docker: `docker compose up -d`
- [ ] Add project-specific documentation
- [ ] READY TO INITIALIZE BMAD (Product Brief, PRD, Architecture, Sprint, Dev Stories, etc.)

## Updating from Template

When the template is updated, you can update your project:

```bash
cd my-existing-project
copier update

# Review changes
git diff

# Commit updates
git add .
git commit -m "Update from template"
```

### Handling Conflicts

If you've customized template files, Copier will:

1. Show you the conflict
2. Let you choose: keep your version, use template version, or merge
3. Mark conflicts for manual resolution

### Selective Updates

```bash
# Update only specific files
copier update --skip "CLAUDE.md" --skip "AGENTS.md"

# Update to specific template version
copier update --vcs-ref=v1.2.0
```

## Customization Tips

### Modifying Generated Files

After generation, customize:

- `CLAUDE.md`: Add project-specific guidance
- `AGENTS.md`: Define agent capabilities
- `docs/GOD.md`: Document event contracts
- `mise.toml`: Add project-specific tasks
- `.env`: Fill in actual credentials

### Ignoring Template Updates

If you want to freeze a file from template updates:

```yaml
# Add to .copier-answers.yml
_skip_if_exists:
  - CLAUDE.md
  - AGENTS.md
```

## Troubleshooting

### Copier Not Found

```bash
# Install globally
uv tool install copier

# Or use pipx
pipx install copier
```

### Template Path Issues

```bash
# Use absolute path for local template
copier copy /path/to/CommonProject my-project

# Or git URL (if published)
copier copy gh:delorenj/CommonProject my-project
```

### Permission Errors

```bash
# Ensure output directory is writable
mkdir -p ~/projects/my-project
copier copy /path/to/CommonProject ~/projects/my-project
```

### Jinja2 Syntax Errors

Check `copier.yml` and `template/*.jinja` files for:

- Unmatched `{% if %}` / `{% endif %}`
- Missing closing `}}`
- Invalid variable names

### Git Hook Issues

After generation:

```bash
# Make hooks executable
chmod +x .git/hooks/*

# Test pre-commit hook
git commit -m "test"  # Should prompt for ticket
```

## Best Practices

1. **Version Control Template**: Keep template in git for tracking changes
2. **Template Versioning**: Tag template releases (v1.0.0, v1.1.0, etc.)
3. **Document Changes**: Maintain CHANGELOG.md for template updates
4. **Test Before Release**: Generate test projects before publishing template updates
5. **Gradual Adoption**: Start with simple projects, add complexity gradually
6. **Feedback Loop**: Collect feedback from generated projects to improve template

## Advanced Usage

### Scripted Project Creation

```bash
#!/bin/bash
# create-33god-component.sh

PROJECT_NAME=$1
PROJECT_TYPE=${2:-software}
LANGUAGE=${3:-python}

copier copy /path/to/CommonProject "$PROJECT_NAME" \
  --data project_name="$PROJECT_NAME" \
  --data project_type="$PROJECT_TYPE" \
  --data primary_language="$LANGUAGE" \
  --data plane_workspace=33god

cd "$PROJECT_NAME"
cp project.env.example .env
mise trust
git init
echo "Project $PROJECT_NAME created!"
```

Usage:

```bash
./create-33god-component.sh "My New Service" software python
```
