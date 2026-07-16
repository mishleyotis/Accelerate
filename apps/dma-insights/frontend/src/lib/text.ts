// Shared text helpers for fields the app renders as RAW TEXT (there is no
// markdown renderer in the tree). LLM/analyst prose leaks markdown emphasis
// (**bold**, __bold__, *italic*) which then shows as literal asterisks on
// cards, why-now signals and conversation starters (2026-07-09 QA). Mirror of
// the backend text_hygiene.strip_md_emphasis so a value cleaned at either the
// generation chokepoint OR the render sink reads identically.

/**
 * Remove markdown emphasis markers, keeping the inner text. Leaves structural
 * markdown (headings, list bullets) untouched — only emphasis leaks as literal
 * `**`. Null/undefined-safe.
 */
export function stripMd(s: string | null | undefined): string {
  if (!s) return "";
  return s
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/__([^_]+)__/g, "$1")
    .replace(/(?<![*\w])\*([^*\n]+)\*(?![*\w])/g, "$1");
}
