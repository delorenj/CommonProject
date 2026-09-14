# CommonProject

Copier template for creating new 33GOD ecosystem components with BMAD methodology, Plane ticket enforcement, and multi-agent development tooling.

## Features

- **Language Support**: Python, TypeScript, Rust
- **Event-Driven Architecture**: Optional [Bloodbank](https://github.com/delorenj/Bloodbank) integration
- **Plane Integration**: `.project.json` for ticket management and project config
- **Ticket Enforcement**: Git hooks enforce Plane ticket requirements
- **Code Review**: `.github/workflows/code-review.yml` reviews every pull request (see [Code Review](#code-review))
- [TODO] **BMAD Integration**: Full BMAD methodology structure by auto running `npx bmad-method@latest install`
- [TODO] Multiple-choice selection for different workflows: BMAD, GSD, GoogleAgentSkills, None.
- **Containerization**: Optional Docker + Docker Compose
- **GOD Documentation**: Auto-generated component documentation
- **Environment Management**: mise.toml + `.env` for reproducible environments
- 1password Secret Value Ready
- **Multi-Agent Tooling**: Pre-configured prompts for Claude, Augment, OpenCode, Gemini, Codex, Copilot, Kimi

## Prerequisites

```bash
# Install Copier
uv tool install copier

# Or with pip
pip install copier

# Set up Plane API key (for automated project creation)
export PLANE_API_KEY="your-plane-api-key"
OR
[TODO] export PLANE_API_KEY=op://VaultName/Key/Field
# Get from: https://plane.delo.sh/<workspace>/settings/api-tokens/
```

## Quick Start

### Option 1: Automated Init (Recommended)

[TODO] One command handles everything: Plane project creation + Copier template:

> TASK - Implement the following:
> Currently, I have to run `copier copy --trust ~/code CommonProject .` globally, or `mise run init-project` while in the CommonProject source dir - but this is not ideal.
> I would rather run `commonProject .` globally.

```bash
# Interactive wizard - creates Plane project automatically
mise run init-project

# Or non-interactive (uses defaults)
mise run init-project-non-interactive

# With custom template
./scripts/init-project.sh --template gh:delorenj/CommonProject
```

The wizard will:

1. Ask for project details (name, description, type)
2. Create the Plane project automatically
3. Run Copier with all answers pre-filled
4. Output next steps

### Option 2: Manual Copier

```bash
# Create new project from template
copier copy gh:delorenj/CommonProject my-new-project

# Or from local template
copier copy /path/to/CommonProject my-new-project

# Answer the interactive questions
# Project will be generated in ./my-new-project/
```

## Skills

Install mise and Node.js 24 or newer. The generated project has one explicit
`mise run skills:sync` task, pinned to `npm:@delorenj/skillex@0.1.1`. It passes
`--scope project --project '{{config_root}}'`, including when invoked from a
nested directory. Global selections may be inherited, but this task writes only
the selected project and Skillex's private XDG receipt state.

Copier runs that task once after rendering. It grants process-local trust to the
rendered config; it does not persist mise trust or run enter/watch hooks.
Configure a canonical Skillex registry first, for example with
`PJ_SKILLS_REGISTRY_ROOT=/path/to/skillex`. A missing registry or invalid selection
fails bootstrap with Skillex's actionable finding instead of silently skipping
activation. The template never clones or copies an alternative skill engine.

Edit `.agents/skills.json` and run the task to apply later selection changes.
Copier refresh preserves existing manifest bytes, including inheritance,
exclusions, and an active pack. Skillex preserves foreign/BMAD content and refuses
conflicting roots; use `skillex migrate` explicitly for legacy layouts. Unrelated
agent hooks remain independently configured.

For template acceptance, install Copier and pytest, then run
`bash .scripts/test-template.sh`. Tests render current tracked template bytes in
canonical `/tmp` fixtures and install the pinned npm release. Before publication,
set `SKILLEX_TEST_TARBALL=/absolute/path/delorenj-skillex-0.1.1.tgz` to test a
prebuilt release candidate without rebuilding or depending on a source checkout.

## Template Questions

The template asks for:

### Basic Configuration

- **Project Name**: Display name (e.g., "HoloCron", "VernonVoice")
- **Project Slug**: Directory/package name (auto-generated from name)
- **Description**: One-sentence project description

### Plane Integration

- **Workspace**: Plane workspace slug (default: 33god)
- **Project Name**
- **Project Identifier**: 2+ character ticket prefix (e.g., HOLO, VERN)

## Post-Generation Steps

> **Tip:** If you used `mise run init-project`, most of this is done automatically!

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
   # Create ticket in Plane (or it was already created for you!)
   # Move to "In Progress"
   git checkout -b <IDENTIFIER>-123-initial-setup
   ```

4. **Start Development**

   ```bash
   # With Docker
   docker compose up -d

   # Without Docker (Python example)
   mise run dev
   ```

## Code Review

Every generated project ships `.github/workflows/code-review.yml`. It is
unconditional — there is no template question to answer and no flag to forget —
so a new project has pull-request review from its first PR.

The workflow runs [`anthropics/claude-code-action@v1`](https://github.com/anthropics/claude-code-action)
on `pull_request` (`opened`, `synchronize`, `ready_for_review`, `reopened`). It
deliberately does **not** use `pull_request_target`, which would expose repo
secrets to code from forked PRs.

### Required secret: `CLAUDE_CODE_OAUTH_TOKEN`

**The workflow does nothing until this secret exists.** Without it the job still
triggers, but the action has no credential and the run fails.

`CLAUDE_CODE_OAUTH_TOKEN` is a long-lived Claude Code OAuth/session token — not a
metered Anthropic API key. Provide it either way:

- **Org-level secret** (preferred): set it once on the GitHub org and grant the
  new repo access. Generated repos inherit it with zero per-repo setup.
- **Repo-level secret**: `Settings → Secrets and variables → Actions → New
  repository secret`, name `CLAUDE_CODE_OAUTH_TOKEN`. Or from the CLI:

  ```bash
  gh secret set CLAUDE_CODE_OAUTH_TOKEN --repo <owner>/<repo>
  ```

Generate the token with `claude setup-token` (Claude Code CLI).

The job requests exactly `contents: read`, `pull-requests: read`,
`issues: read`, and `id-token: write` — read-only on the repo, with OIDC for the
action's own auth exchange.

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

Root-level files describe the template itself. Files in `template/` are what Copier renders into generated projects. See `AGENTS.md` for full development guidance.

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
4. Update AGENTS.md template with language-specific guidance
