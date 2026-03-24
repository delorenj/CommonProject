# CLAUDE.md

This file provides guidance to Claude Code when working on the **CommonProject template repo** itself.

This is NOT a generated project. This is the Copier template source that generates new 33GOD ecosystem projects.

## Repo Structure

```
CommonProject/
├── copier.yml              # Template questions and configuration
├── template/               # What Copier renders into new projects
│   ├── _bmad/              # Full BMAD system (pre-initialized)
│   ├── .augment/           # Augment CLI commands
│   ├── .claude/            # Claude Code commands, hooks, personalities
│   ├── .codex/             # Codex CLI prompts
│   ├── .crush/             # CRUSH protocol commands
│   ├── .gemini/            # Gemini CLI commands
│   ├── .opencode/          # OpenCode CLI commands
│   ├── CLAUDE.md.jinja     # Generated project's CLAUDE.md
│   ├── AGENTS.md.jinja     # Generated project's AGENTS.md
│   ├── mise.toml.jinja     # Generated project's mise config
│   ├── .plane.json.jinja   # Plane project config (rendered)
│   ├── project.env.example.jinja
│   └── ...                 # Conditional: Dockerfile, docker-compose, GOD docs
├── _bmad/                  # BMAD system (root copy, for template-dev use)
├── .scripts/               # Template testing utilities
├── README.md               # Template usage documentation
├── TEMPLATE_USAGE.md       # Detailed template variable reference
└── CLAUDE.md               # THIS FILE (template-dev guidance)
```

## Key Concepts

### Two-Layer Separation

Root-level files describe the template itself. Files in `template/` are what Copier renders into generated projects. The `_subdirectory: template` setting in `copier.yml` enforces this boundary.

- **Root `README.md`** = "How to use this template"
- **`template/CLAUDE.md.jinja`** = The generated project's CLAUDE.md

### How Copier Processes Files

- Files ending in `.jinja` get Jinja2 processed (variables substituted, conditionals evaluated, suffix stripped)
- All other files are copied verbatim (this is how 500+ BMAD files and CLI coder configs transfer untouched)
- Filenames can contain Jinja2 conditionals: `{% if uses_docker %}Dockerfile{% endif %}.jinja`

### Template Variables

All template variables are defined in `copier.yml`. Jinja2 templates reference these via `{{ variable_name }}`. Conditionals like `{% if has_hardware %}` control optional sections.

### Plane Integration

Project config lives in `.plane.json` (rendered from `.plane.json.jinja`). Runtime secrets and service URLs go in `.env` (copied from `project.env.example`). There is no `.plane.env`.

### BMAD System

The `template/_bmad/` directory contains the full BMAD methodology pre-initialized. Generated projects do NOT need to run `npx bmad-method install`. The only templatized file is `_bmad/bmm/config.yaml.jinja` which injects `project_name`, `user_name`, and `user_skill_level`.

## Development Workflow

### Adding a New Template Variable

1. Add the question to `copier.yml`
2. Use the variable in `template/*.jinja` files as needed
3. Update TEMPLATE_USAGE.md variable reference table
4. Add a test case in `.scripts/test-template.sh`

### Testing Template Changes

```bash
# Generate test projects for all project types
bash .scripts/test-template.sh

# Test a single scenario manually
copier copy . /tmp/test-project --overwrite
```

### What Belongs in This Repo

- Template logic (copier.yml, .jinja files)
- BMAD system (pre-init state, in template/)
- CLI coder prompts and hooks (in template/)
- Template testing scripts
- Generic mise.toml with agnostic sections

### What Does NOT Belong

- Any reference to a specific project (TonnyBox, HoloCron, etc.)
- Rendered/hydrated content with concrete values
- Project-specific tech stacks or framework choices
- Anything that only makes sense after template generation
- References to `.plane.env` (use `.plane.json` for Plane config, `.env` for secrets)
