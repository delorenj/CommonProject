# CommonProject

Copier template for creating new 33GOD ecosystem components with BMAD methodology, Plane ticket enforcement, and multi-agent development tooling.

## Features

- **Multiple Project Types**: Software, Hardware, Dashboard, Tooling
- **Language Support**: Python, TypeScript, Rust
- **Event-Driven Architecture**: Optional Bloodbank (RabbitMQ) integration
- **Plane Integration**: `.plane.json` for ticket management and project config
- **Ticket Enforcement**: Git hooks enforce Plane ticket requirements
- **BMAD Integration**: Full BMAD methodology structure
- **Containerization**: Optional Docker + Docker Compose
- **GOD Documentation**: Auto-generated component documentation
- **Environment Management**: mise.toml + `.env` for reproducible environments
- **Multi-Agent Tooling**: Pre-configured prompts for Claude, Augment, OpenCode, Gemini, Codex, Copilot, Kimi

## Prerequisites

```bash
# Install Copier
uv tool install copier

# Or with pip
pip install copier
```

## Quick Start

```bash
# Create new project from template
copier copy gh:delorenj/CommonProject my-new-project

# Or from local template
copier copy /path/to/CommonProject my-new-project

# Answer the interactive questions
# Project will be generated in ./my-new-project/
```

## Template Questions

The template asks for:

### Basic Configuration
- **Project Name**: Display name (e.g., "HoloCron", "VernonVoice")
- **Project Slug**: Directory/package name (auto-generated from name)
- **Description**: One-sentence project description
- **Project Type**: software, hardware, dashboard, or tooling

### Hardware Configuration (conditional, if project_type == hardware)
- **Hardware Platform**: e.g., "Raspberry Pi Zero 2 W", "ESP32"
- **Hardware Hostname**: SSH hostname (default: {slug}.local)
- **Hardware Peripherals**: Comma-separated list

### Agent Configuration
- **Has Agent**: Whether component has a dedicated AI agent
- **Agent Name**: Agent display name
- **Agent Role**: Agent purpose/role description

### Plane Integration
- **Workspace**: Plane workspace slug (default: 33god)
- **Project ID**: From Plane project settings
- **Project Identifier**: 2+ character ticket prefix (e.g., HOLO, VERN)

### Technical Stack
- **Primary Language**: python, typescript, or rust
- **Uses Docker**: Enable containerization
- **Uses Event Bus**: Bloodbank integration
- **Additional Services**: Comma-separated (postgres, redis, qdrant)

### Documentation
- **Initialize GOD Docs**: Create GOD documentation structure
- **Component Domain**: Which 33GOD domain (infrastructure, agent-orchestration, etc.)

## Generated Structure

```
my-new-project/
├── _bmad/                    # BMAD methodology (pre-initialized)
│   ├── bmb/                  # BMAD Builder
│   ├── bmm/                  # BMAD Method Management
│   ├── cis/                  # Creative Innovation Suite
│   ├── core/                 # Core BMAD resources
│   └── custom/               # Custom workflows
├── .augment/                 # Augment CLI commands
├── .claude/                  # Claude Code commands, hooks, personalities
├── .codex/                   # Codex CLI prompts
├── .crush/                   # CRUSH protocol commands
├── .gemini/                  # Gemini CLI commands
├── .opencode/                # OpenCode CLI commands
├── docs/                     # GOD documentation (if enabled)
│   └── GOD.md
├── .plane.json               # Plane project configuration
├── AGENTS.md                 # Agent context and rules
├── CLAUDE.md                 # Claude Code guidance
├── mise.toml                 # Environment + task runner
├── project.env.example       # Runtime env template (copy to .env)
├── docker-compose.yml        # Container orchestration (if Docker enabled)
├── Dockerfile                # Container build (if Docker enabled)
└── README.md                 # Project README
```

## Post-Generation Steps

1. **Initialize Environment**
   ```bash
   cd my-new-project
   cp project.env.example .env
   # Edit .env with actual values (API keys, service URLs)
   mise trust
   ```

2. **Initialize Git**
   ```bash
   git init
   git add .
   git commit -m "Initial commit from template"
   ```

3. **Create Plane Ticket**
   ```bash
   # Create ticket in Plane
   # Move to "In Progress"
   git checkout -b PROJ-123-initial-setup
   ```

4. **Start Development**
   ```bash
   # With Docker
   docker compose up -d

   # Without Docker (Python example)
   mise run dev
   ```

## Updating Existing Projects

Copier supports updating projects when the template changes:

```bash
cd my-existing-project
copier update

# Or to a specific template version
copier update --vcs-ref=v1.2.0
```

## Template Development

### Repo Structure

Root-level files describe the template itself. Files in `template/` are what Copier renders into generated projects. See `CLAUDE.md` for full development guidance.

### Testing

```bash
# Run all template test scenarios
bash .scripts/test-template.sh

# Test a single scenario
copier copy . /tmp/test-project --overwrite
```

### Adding New Project Types

1. Add to `project_type` choices in `copier.yml`
2. Update conditional sections in `template/*.jinja` files
3. Add type-specific questions if needed
4. Update GOD.md template with type-specific content
5. Add test case in `.scripts/test-template.sh`

### Adding Language Support

1. Add to `primary_language` choices in `copier.yml`
2. Create Dockerfile variant in templates
3. Add mise.toml tasks
4. Update CLAUDE.md template with language-specific guidance

## Architecture Decisions

### Why Copier?
- **Update Support**: Projects can receive template updates via `copier update`
- **Powerful Templating**: Jinja2 for complex conditional logic
- **Interactive**: Question-based configuration
- **Version Control**: Track template versions in generated projects

### Why Two-Layer Separation?
- Root level = template meta-docs (this README, CLAUDE.md for template dev)
- `template/` = what gets rendered (`_subdirectory: template` in copier.yml)
- Prevents collision between template docs and generated project docs

## License

[Add license information]

## Support

- **Plane**: https://plane.delo.sh/33god/
