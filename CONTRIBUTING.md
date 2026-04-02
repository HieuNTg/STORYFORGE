# Contributing to StoryForge

Thank you for your interest in contributing! StoryForge is a community-driven project and we welcome contributions of all kinds — bug fixes, new features, documentation improvements, and more. This guide will get you up and running quickly.

---

## Development Setup

### Prerequisites

- Python 3.10+
- Node.js 18+ (for frontend asset building)
- Git
- Docker (optional, for container-based development)

### Fork & Clone

```bash
# Fork the repo on GitHub, then:
git clone https://github.com/<your-username>/STORYFORGE.git
cd STORYFORGE
```

### Install Dependencies

```bash
# Backend
pip install -r requirements.txt
pip install -r requirements-test.txt   # test dependencies

# Frontend (Tailwind CSS build)
npm install
```

### Run the Development Server

```bash
python app.py
# → http://localhost:7860
```

The server reloads automatically when you change Python files (Uvicorn `--reload` mode).

### Run Tests

```bash
python -m pytest tests/
```

To run a specific test file or directory:

```bash
python -m pytest tests/test_pipeline.py -v
python -m pytest tests/integration/ -v
```

To run with coverage:

```bash
python -m pytest tests/ --cov=pipeline --cov=services --cov=api
```

### Run Linting

```bash
ruff check .
ruff format --check .
```

---

## Code Style

Consistency keeps the codebase readable for everyone. Please follow these guidelines:

- **Linter:** [ruff](https://docs.astral.sh/ruff/) — run `ruff check .` before committing
- **Formatter:** ruff format (or Black-compatible) — run `ruff format .`
- **File length:** keep files under 200 lines; split large modules into focused sub-modules
- **Filenames:** `kebab-case` for new files where the framework permits (e.g. `drama-utils.py`); follow existing naming in each directory
- **Docstrings:** write descriptive docstrings for all public functions and classes
- **Type hints:** use Python type annotations for all function signatures
- **Imports:** standard library first, then third-party, then local — separated by blank lines
- **No magic numbers:** extract constants with descriptive names

### Example

```python
def score_chapter(text: str, dimensions: list[str]) -> dict[str, float]:
    """Score a chapter across multiple quality dimensions using LLM-as-judge.

    Args:
        text: Raw chapter text to evaluate.
        dimensions: List of dimension names (e.g. ["coherence", "drama"]).

    Returns:
        Mapping of dimension name to score in range [0.0, 1.0].
    """
    ...
```

---

## Pull Request Process

### 1. Create a Feature Branch

```bash
git checkout -b feat/your-feature-name
# or
git checkout -b fix/short-description
```

### 2. Make Your Changes

- Write or update tests for any new behavior (place them in `tests/`)
- Keep each PR focused on **one feature or fix**
- Update `docs/` if your change affects architecture or public APIs

### 3. Verify Before Submitting

```bash
ruff check .          # no lint errors
ruff format --check . # no formatting issues
python -m pytest tests/ -q  # all tests pass
```

### 4. Commit with Conventional Messages

Use the [Conventional Commits](https://www.conventionalcommits.org/) format:

```
feat: add Ollama streaming support
fix: handle empty chapter text in quality scorer
docs: update architecture diagram in README
refactor: extract prompt templates into services/prompts/
test: add unit tests for drama simulation rounds
```

### 5. Open the Pull Request

- Use the PR template (filled in automatically)
- Reference the related issue: `Closes #123`
- Keep the PR description concise but complete
- Request a review and respond to feedback promptly

---

## Architecture Overview

Understanding where things live will help you find the right place for your changes:

| Directory | Responsibility |
|:----------|:---------------|
| `pipeline/` | 3-layer generation engine (story → drama → storyboard) and AI agent graph |
| `services/` | Reusable business logic: LLM client, quality scorer, exporters, TTS, auth |
| `api/` | FastAPI route handlers — thin layer that calls into `services/` and `pipeline/` |
| `web/` | Alpine.js single-page application and Tailwind CSS frontend |
| `middleware/` | Cross-cutting concerns: JWT auth, rate limiting, audit logging, metrics |
| `models/` | Pydantic schemas shared across layers |
| `tests/` | All automated tests — mirrors source directory structure |

Key design rules:
- `api/` handlers should stay thin — business logic belongs in `services/`
- `pipeline/` layers communicate through well-defined Pydantic models
- Agents in `pipeline/agents/` are stateless and receive all context as arguments
- No circular imports — `pipeline/` may import from `services/`, never the reverse

---

## Good First Issues

Looking for a place to start? Check the
[`good first issue`](https://github.com/HieuNTg/STORYFORGE/labels/good%20first%20issue)
label on GitHub for beginner-friendly tasks.

For broader discussion, feature ideas, or questions — open a
[GitHub Discussion](https://github.com/HieuNTg/STORYFORGE/discussions)
rather than an issue.

---

## Code of Conduct

Be respectful and welcoming to all contributors. We follow the
[Contributor Covenant](https://www.contributor-covenant.org/) code of conduct.
Harassment or exclusionary behavior will not be tolerated.

---

Thank you for helping make StoryForge better for everyone!
