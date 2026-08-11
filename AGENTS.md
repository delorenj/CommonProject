# CLAUDE.md

This file provides guidance to Claude Code when working on the **CommonProject template repo** itself.

This is NOT a generated project. This is the Copier template source that generates new projects.

## Repo Structure

```
CommonProject/
├── copier.yml              # Template questions (just name + description)
├── template/               # What Copier renders into new projects
│   ├── .agents/            # Shared skill/hook source inputs
│   ├── .mise/tasks/        # File-based mise tasks
│   ├── .mise/scripts/      # Managed lifecycle scripts
│   ├── .scripts/           # Post-generation utilities
│   │   └── setup-plane.py  # Creates Plane project + ticket_provider block in .project.json
│   ├── AGENTS.md.jinja     # Generated project's agent SSOT
│   ├── CLAUDE.md           # Symlink → AGENTS.md
│   ├── GEMINI.md           # Symlink → AGENTS.md
│   └── mise.toml.jinja     # Generated project's mise config
├── _bmad/                  # Template-repo development methodology only
├── .scripts/               # Template testing utilities
└── CLAUDE.md               # THIS FILE (template-dev guidance)
```

## Key Concepts

### Two-Layer Separation

Root-level files describe the template itself. Files in `template/` are what Copier renders into generated projects. The `_subdirectory: template` setting in `copier.yml` enforces this boundary.

### How Copier Processes Files

- Files ending in `.jinja` get Jinja2 processed (variables substituted, suffix stripped)
- All other files are copied verbatim (this is how 500+ BMAD files and CLI coder configs transfer untouched)

### Template Variables

Only two questions asked: `project_name` and `project_description`. Everything else is derived or automated:
- `project_slug` derived from project_name
- Plane project created via API in post-generation task
- .gitignore copied from ~/.config/git/ignore

### Post-Generation Tasks (copier.yml `_tasks`)

After rendering, Copier automatically:
1. Copies .gitignore from ~/.config/git/ignore
2. Makes scripts executable
3. Runs setup-plane.py (creates Plane project, writes the ticket_provider block in .project.json)
4. Leaves lifecycle audit and Git initialization to pjangler

### BMAD System

CommonProject does not vendor installer-generated BMAD output. The pjangler
lifecycle installs BMAD after Copier rendering with exactly the six supported
tools: Claude, Codex, Gemini, Copilot, OpenCode, and Kimi. It then audits the
result before initializing Git.

## Development Workflow

### Testing Template Changes

```bash
copier copy . /tmp/test-project --overwrite
```

### What Belongs in This Repo

- Template logic (copier.yml, .jinja files)
- Minimal source inputs consumed by pjangler lifecycle recipes
- CLI coder prompts and hooks (in template/)
- Post-generation scripts (in template/.scripts/)
- Template testing scripts

### What Does NOT Belong

- Any reference to a specific project (TonnyBox, HoloCron, etc.)
- Rendered/hydrated content with concrete values
- Installer-generated BMAD snapshots under `template/_bmad/`
- Unsupported CLI integration roots
- Project-specific tech stacks or framework choices
- Anything that only makes sense after template generation
