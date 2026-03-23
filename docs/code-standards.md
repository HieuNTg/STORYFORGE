# Code Standards & Project Conventions

## Language & Framework

- **Language**: Python 3.10+
- **Web Framework**: Flask (lightweight API server)
- **Data Validation**: Pydantic v2 (type-safe models)
- **LLM Integration**: OpenAI Python SDK (OpenAI-compatible endpoints)
- **Async**: ThreadPoolExecutor for parallelism (no async/await)

## Code Organization

### File Structure Rules

```
module/
├── __init__.py                      # Exports main classes
├── core_class.py                    # Primary class (80% of logic)
├── helper.py                        # Utilities, validators
└── schemas.py                       # Data models (models/ folder only)
```

### Naming Conventions

| Item | Style | Example |
|------|-------|---------|
| **Classes** | PascalCase | `StoryGenerator`, `LLMClient`, `CharacterState` |
| **Functions** | snake_case | `generate_characters()`, `extract_plot_events()` |
| **Constants** | UPPER_SNAKE_CASE | `MAX_RETRIES`, `BASE_DELAY` |
| **Private methods** | _leading_underscore | `_format_context()`, `_get_client()` |
| **Module names** | snake_case | `llm_client.py`, `agent_registry.py` |
| **Boolean vars** | is_/has_/auto_ prefix | `cache_enabled`, `auto_fallback` |

### Import Organization

```python
# Standard library
import json
import logging
from typing import Optional, Generator
from concurrent.futures import ThreadPoolExecutor

# Third-party
from pydantic import BaseModel, Field
from openai import OpenAI

# Local
from models.schemas import Chapter, StoryContext
from services.llm_client import LLMClient
```

## Model & Schema Standards

### Pydantic Models (models/schemas.py)

**Structure**:
```python
class ModelName(BaseModel):
    """Brief docstring."""
    field_name: FieldType = Field(
        default=default_value,
        description="Human-readable field description"
    )
```

**Conventions**:
- All fields must have descriptions (for LLM understanding)
- Use `Field(default_factory=list)` for mutable defaults
- Optional fields use `Optional[Type]` (not `Type = None`)
- Enums for controlled values (e.g., role: "protagonist" | "antagonist")

**Example**:
```python
class CharacterState(BaseModel):
    """Trạng thái nhân vật thay đổi theo chương."""
    name: str
    mood: str = Field(default="", description="Current emotional state")
    arc_position: str = Field(default="", description="Story arc stage")
    knowledge: list[str] = Field(default_factory=list, description="Known facts")
```

## Configuration Standards

### ConfigManager Pattern

- **Access**: Via singleton `ConfigManager()`
- **Files**: `data/config.json` (user) + in-code defaults
- **Structure**: Nested dataclasses (LLMConfig, PipelineConfig)
- **Thread-safe**: Lazy init with lock

**Usage**:
```python
config = ConfigManager()
temperature = config.llm.temperature
context_window = config.pipeline.context_window_chapters
```

## Function & Method Standards

### Docstrings

**Format**: Google-style (triple quotes)
```python
def extract_character_states(self, content: str, characters: list[Character]) -> list[CharacterState]:
    """Extract character states from chapter content.

    Args:
        content: Chapter text (will be excerpted for LLM)
        characters: List of characters to track

    Returns:
        List of CharacterState objects with mood, arc, knowledge, etc.
        Returns empty list if extraction fails (logs warning).

    Raises:
        None (failures logged, not raised)
    """
```

### Return Types

- **Multiple values**: Tuple or dict, not multiple returns
- **Optional result**: Use `Optional[Type]` or default fallback
- **Error handling**: Log + return empty/default, rarely raise

```python
# Good
def summarize_chapter(self, content: str) -> str:
    try:
        return self.llm.generate(...)
    except Exception as e:
        logger.warning(f"Summary failed: {e}")
        return ""  # Fallback

# Avoid
def summarize_chapter(self, content: str) -> str:
    return self.llm.generate(...)  # Unhandled exceptions
```

## Logging Standards

### Logger Setup

```python
import logging
logger = logging.getLogger(__name__)

# In functions:
logger.info(f"Starting task...")
logger.warning(f"Non-critical issue: {e}")
logger.debug(f"Detailed debug: {var}")
logger.error(f"Error: {e}")  # For errors, not exceptions
```

### Log Levels

| Level | Use Case | Example |
|-------|----------|---------|
| `DEBUG` | Development details | Variable values, LLM token counts |
| `INFO` | User-relevant progress | "Generating chapter 3...", "Cache hit" |
| `WARNING` | Recoverable errors | "Extraction failed, using fallback" |
| `ERROR` | Critical but handled | "LLM call failed after 3 retries" |

## Parallel Execution Standards

### ThreadPoolExecutor Usage

```python
with ThreadPoolExecutor(max_workers=3) as executor:
    summary_f = executor.submit(self.summarize_chapter, chapter.content)
    states_f = executor.submit(self.extract_character_states, chapter.content, characters)
    events_f = executor.submit(self.extract_plot_events, chapter.content, ch_num)

    # Collect results with fallbacks
    try:
        summary = summary_f.result()
    except Exception as e:
        logger.warning(f"Summary extraction failed: {e}")
        summary = ""

    # Always provide fallback
    try:
        new_states = states_f.result()
    except Exception as e:
        logger.warning(f"State extraction failed: {e}")
        new_states = []
```

**Rules**:
- Always wrap `result()` in try-except
- Provide sensible fallback (empty string, empty list, None)
- Log warnings for failures (errors are acceptable)
- No task cancellation; let threads finish

## LLM Integration Standards

### Prompt Design

**Structure**:
1. System prompt: Role + output format
2. User prompt: Data + task
3. Temperature: 0.8 for generation, 0.3 for extraction
4. max_tokens: Limit output size

```python
self.llm.generate_json(
    system_prompt="You are a character analyst. Return JSON.",
    user_prompt=prompts.EXTRACT_CHARACTER_STATE.format(
        content=content_excerpt,
        characters=char_list_text
    ),
    temperature=0.3,  # Low for consistency
    max_tokens=1000,  # Compact extraction
)
```

### LLMClient Methods

**`generate()`**: Raw text generation
```python
text = self.llm.generate(
    system_prompt="...",
    user_prompt="...",
    temperature=0.8,
    max_tokens=4096,
    json_mode=False,
)
```

**`generate_json()`**: Structured output
```python
result = self.llm.generate_json(
    system_prompt="...",
    user_prompt="...",
    temperature=0.3,
    max_tokens=1000,  # Compact
)
# Returns: dict (validated)
```

## Testing & Validation

### Schema Validation

```python
# Pydantic auto-validates on instantiation
try:
    state = CharacterState(**raw_data)
except Exception as e:
    logger.debug(f"Invalid state: {e}")
    # Skip and continue
```

### Configuration Validation

- Load from JSON → apply to dataclass fields
- Type coercion automatic (int to str, etc.)
- Missing keys → use defaults
- Extra keys → ignored

## Error Handling Philosophy

### Principles

1. **Fail gracefully**: Log + fallback rather than crash
2. **No silent failures**: Always log something
3. **Predictable defaults**: Empty list/string/None, never random
4. **Propagate rarely**: Only for critical setup errors

### Patterns

**Pattern 1: LLM Call with Fallback**
```python
try:
    result = self.llm.generate_json(...)
except Exception as e:
    logger.warning(f"LLM call failed: {e}")
    result = {}  # Empty fallback
```

**Pattern 2: Model Instantiation**
```python
try:
    state = CharacterState(**raw_data)
    states.append(state)
except Exception as e:
    logger.debug(f"Skipping invalid entry: {e}")
    # Continue to next
```

**Pattern 3: File I/O**
```python
try:
    with open(config_path) as f:
        data = json.load(f)
except Exception as e:
    logger.warning(f"Config load error: {e}")
    # Use defaults from class
```

## Performance & Efficiency

### Token Budgets

| Operation | Temp | Max Tokens | Use Case |
|-----------|------|-----------|----------|
| Chapter writing | 0.8 | 4096 | Full chapter generation |
| Summarization | 0.7 | 500 | Quick recap |
| Character extraction | 0.3 | 1000 | Consistent state |
| Plot extraction | 0.3 | 1000 | Event tracking |

### Caching

- **Enabled by default**: `cache_enabled=true` in LLMConfig
- **TTL**: `cache_ttl_days=7` (configurable)
- **Key**: Hash of (system_prompt + user_prompt + model config)
- **Eviction**: Automatic on startup, on-demand removal

### Memory Management

- **Rolling context**: Cap at `context_window_chapters` summaries
- **Plot events**: Max 50 stored (prevents unbounded growth)
- **Character states**: Overwritten per chapter (no accumulation)

## Export & File I/O Standards

### Export Methods Pattern

**Multi-file export**:
```python
def export_output(self, output_dir: str, formats: list[str] | None = None) -> list[str]:
    """Generate files in specified formats.

    Returns:
        List of created file paths (empty list if nothing generated)
    """
    files = []
    # Generate each format
    if "TXT" in formats:
        path = os.path.join(output_dir, f"{timestamp}_{type}.txt")
        # Write file
        files.append(path)
    return files  # Always return list, even if empty
```

**Bundled export**:
```python
def export_zip(self, output_dir: str, formats: list[str] | None = None) -> str:
    """Bundle all exports into ZIP.

    Returns:
        ZIP file path (empty string if no files)
    """
    files = self.export_output(output_dir, formats)
    if not files:
        return ""  # Graceful empty response
    # Create ZIP
    return zip_path
```

**Optional export**:
```python
def _export_markdown(self, output_dir: str, timestamp: str) -> Optional[str]:
    """Export story as Markdown.

    Returns:
        File path if created, None otherwise
    """
    if not self.output.story:
        return None
    # Write file
    return path
```

### Gradio File Widget Pattern

```python
# UI definition
export_files_output = gr.File(
    label="File xuất", file_count="multiple"
)

# Handler: paths to file paths
def export_handler(orch, formats):
    if orch is None:
        return None
    try:
        paths = orch.export_output(formats=formats)
        return paths if paths else None  # gr.File expects list or None
    except Exception as e:
        logger.error(f"Export failed: {e}")
        return None

# Event binding
export_btn.click(
    fn=export_handler,
    inputs=[orchestrator_state, export_formats],
    outputs=[export_files_output]
)
```

## API & Flask Standards

### Endpoint Structure

```python
@app.route('/api/resource', methods=['POST'])
def endpoint():
    """Docstring with brief description."""
    try:
        data = request.json
        # Validation
        if not data.get('required_field'):
            return {"error": "Missing field"}, 400
        # Processing
        result = process(data)
        return {"data": result, "status": "success"}, 200
    except Exception as e:
        logger.error(f"Endpoint error: {e}")
        return {"error": "Server error"}, 500
```

### Response Format

```json
{
  "status": "success" | "error",
  "data": { /* result */ },
  "error": "Error message (if any)",
  "timestamp": "ISO 8601"
}
```

## Git & Version Control

### Commit Messages

- **Format**: `type(scope): description`
- **Types**: feat, fix, refactor, docs, test, chore
- **Scope**: layer (layer1, layer2, llm_client, etc.)
- **Description**: What & why, not how

**Examples**:
```
feat(layer1): Add character state extraction with rolling context
fix(llm_client): Handle timeout errors in fallback logic
refactor(schema): Consolidate plot event structure
docs(architecture): Update Layer 1 flow diagram
```

### Branch Naming

- `feat/{feature-name}` — New feature
- `fix/{bug-name}` — Bug fix
- `refactor/{scope}` — Code cleanup
- `docs/{section}` — Documentation only

---

**Last Updated**: 2026-03-23 (Phase 4: Export & Download) | **Version**: 1.1
