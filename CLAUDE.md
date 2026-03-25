# CLAUDE.md

This file provides guidance to Claude Code when working on the **CommonProject template repo** itself.

This is NOT a generated project. This is the Copier template source that generates new projects.

## Repo Structure

```
CommonProject/
├── copier.yml              # Template questions (just name + description)
├── template/               # What Copier renders into new projects
│   ├── _bmad/              # Full BMAD system (pre-initialized)
│   ├── .augment/           # Augment CLI commands
│   ├── .claude/            # Claude Code config
│   ├── .codex/             # Codex CLI prompts
│   ├── .crush/             # CRUSH protocol commands
│   ├── .gemini/            # Gemini CLI commands
│   ├── .opencode/          # OpenCode CLI commands
│   ├── .agentvibes/        # AgentVibes config
│   ├── .mise/tasks/        # File-based mise tasks
│   ├── .scripts/           # Post-generation utilities
│   │   └── setup-plane.sh  # Creates Plane project + .plane.json
│   ├── CLAUDE.md.jinja     # Generated project's CLAUDE.md
│   └── mise.toml.jinja     # Generated project's mise config
├── _bmad/                  # BMAD system (root copy, for template-dev use)
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
- `user_name` / `user_skill_level` hardcoded for BMAD config
- Plane project created via API in post-generation task
- .gitignore copied from ~/.config/git/ignore
- git init + initial commit run automatically

### Post-Generation Tasks (copier.yml `_tasks`)

After rendering, Copier automatically:
1. Copies .gitignore from ~/.config/git/ignore
2. Makes scripts executable
3. Runs setup-plane.sh (creates Plane project, writes .plane.json)
4. Runs git init + git add -A + git commit

### BMAD System

The `template/_bmad/` directory contains the full BMAD methodology pre-initialized. Generated projects do NOT need to run `npx bmad-method install`. The only templatized file is `_bmad/bmm/config.yaml.jinja` which injects `project_name`, `user_name`, and `user_skill_level`.

## Development Workflow

### Testing Template Changes

```bash
copier copy . /tmp/test-project --overwrite
```

### What Belongs in This Repo

- Template logic (copier.yml, .jinja files)
- BMAD system (pre-init state, in template/)
- CLI coder prompts and hooks (in template/)
- Post-generation scripts (in template/.scripts/)
- Template testing scripts

### What Does NOT Belong

- Any reference to a specific project (TonnyBox, HoloCron, etc.)
- Rendered/hydrated content with concrete values
- Project-specific tech stacks or framework choices
- Anything that only makes sense after template generation
