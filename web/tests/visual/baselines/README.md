# Visual Regression Baselines

Pre-redesign screenshot baselines for the StoryForge "The Forge" UI/UX redesign (M1).

## Status

Baselines NOT YET CAPTURED — the FastAPI backend must be running to capture them.

## How to capture

```bash
# 1. Start the backend
python app.py   # http://localhost:7860

# 2. Run the baseline spec
npx playwright test web/tests/visual/baselines.spec.ts

# 3. Screenshots appear here as:
#    pipeline-light.png  pipeline-dark.png
#    library-light.png   library-dark.png
#    settings-light.png  settings-dark.png
#    branching-light.png branching-dark.png
#    analytics-light.png analytics-dark.png
#    export-light.png    export-dark.png
#    account-light.png   account-dark.png
```

## Coverage

| Page       | Light | Dark |
|------------|-------|------|
| pipeline   | -     | -    |
| library    | -     | -    |
| settings   | -     | -    |
| branching  | -     | -    |
| analytics  | -     | -    |
| export     | -     | -    |
| account    | -     | -    |

Update this table after capture: replace `-` with the commit SHA where baselines were captured.

## Notes

- Baselines are committed to git as PNG files (not gitignored).
- `web/js/**/*.png` is NOT in `.gitignore` — baselines are intentionally tracked.
- Axe-core a11y audit runs during capture but violations are non-blocking for the snapshot itself.
- Future PR checks will compare against these baselines via `npx playwright test --update-snapshots=never`.
