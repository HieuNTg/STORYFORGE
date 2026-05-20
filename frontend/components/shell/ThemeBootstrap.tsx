/**
 * Inline theme bootstrap — sets `class="dark"` on <html> before paint to avoid FOUC.
 *
 * Reads `localStorage.sf_theme` (`'dark' | 'light' | null`). Cinema-gold default:
 * unrecognized / null → dark. Only the literal string `'light'` switches to light.
 * Also sets `document.documentElement.style.colorScheme` so native form controls
 * and scrollbars match the resolved theme.
 *
 * Uses a raw <script> element (not next/script) so the IIFE executes synchronously
 * in <head> before CSS evaluates `.dark` selectors → no FOUC even on slow devices.
 * Must be rendered inside `app/layout.tsx`'s `<head>`.
 */
export function ThemeBootstrap() {
  const bootstrap = `(function(){try{var k='sf_theme',s=localStorage.getItem(k),d=s==='dark'||(s!=='light'),r=document.documentElement;if(d){r.classList.add('dark');}else{r.classList.remove('dark');}r.style.colorScheme=d?'dark':'light';}catch(e){}})();`;

  return (
    <script
      id="sf-theme-bootstrap"
      dangerouslySetInnerHTML={{ __html: bootstrap }}
    />
  );
}

export default ThemeBootstrap;
