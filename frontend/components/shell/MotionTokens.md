# Motion Tokens (StoryForge UI)

Defined in `app/globals.css` `:root`. **No `animation-iteration-count: infinite` anywhere.**
All motion respects `prefers-reduced-motion: reduce` (durations zero out automatically).

## Easing

| Token | Curve | Use for |
|---|---|---|
| `--ease-emphasized` | `cubic-bezier(0.2, 0, 0, 1)` | Page/route enter, drawer/sheet open, modal mount. The default. |
| `--ease-out` | `cubic-bezier(0, 0, 0.2, 1)` | Quick UI feedback: hover lift, button press release, tooltip fade. |

## Durations

| Token | Value | Use for |
|---|---|---|
| `--duration-fast` | `120ms` | Hover/focus tint, icon swap, color change. Anything under cursor. |
| `--duration-base` | `200ms` | Page enter, modal/sheet open, dropdown reveal, tab switch. **Default.** |
| `--duration-slow` | `320ms` | Larger layout shifts (sidebar collapse, multi-element route transition). **Hard ceiling — never exceed.** |

## Rules

1. **Single-shot only.** No looping spinners as engagement; use `<Progress>` with a known endpoint or a determinate `aria-busy` indicator.
2. **One animation per interaction.** If hover triggers tint + lift + shadow, share the same `--duration-fast` + `--ease-out` — do not stagger.
3. **Page enter is opacity 0→1 only.** Already wired in `body { animation: sf-page-enter ... }`. Do not add transforms to body.
4. **Reduced motion = zero, not "subtle".** Users who opt out get instant snaps. Don't compromise by halving durations.
5. **Transforms over layout.** Animate `opacity`, `transform: translate/scale`. Never animate `width`, `height`, `top`, `left` (jank).

## Keyframes

| Keyframe | Duration | Use for |
|---|---|---|
| `gold-pulse` | 2s infinite | Subtle cinema gold glow (sidebar brand, accent highlights). Respects `prefers-reduced-motion`. |

## FadeIn Primitive (motion@^12)

`<FadeIn />` wraps child content with `opacity: 0` → `1` over `--duration-base` using `--ease-emphasized`. Always use for content that mounts dynamically (modals, route transitions, lazy panels).

```tsx
import { FadeIn } from '@/components/motion/FadeIn';

<FadeIn>
  <YourContent />
</FadeIn>
```

## Examples

```tsx
// Hover lift on Card
className="transition-[transform,box-shadow] duration-[var(--duration-fast)] ease-[var(--ease-out)] hover:-translate-y-px"

// Sheet enter
className="data-[state=open]:animate-in data-[state=open]:duration-[var(--duration-base)] data-[state=open]:ease-[var(--ease-emphasized)]"

// Cinema gold pulse on accent
className="animate-[gold-pulse] duration-[2s]"
```
