# Product Guidelines

## Voice and Tone
- **Professional & Operational:** Communication should be direct, precise, and focused on infrastructure health. 
- **Action-Oriented:** Errors and notifications should clearly state the impact and the recommended action.

## UX Principles
- **Data Density & Readability:** Maximize the visibility of massive CIDR blocks. Use the Canonical Hierarchical Tree-Table to present data compactly.
- **Responsiveness:** Operations should feel immediate. Use streaming responses (SSE) to display scan results in real-time.
- **Filtering First:** The UI must prioritize powerful filtering to isolate specific services or IP ranges.

## UI / Branding
- **Design System:** Rely on `shadcn/ui` components for a clean, modern, and accessible interface.
- **Status Indicators:** Use standard conventions (e.g., green for healthy, red for errors, gray for void) consistently.

## Domain Rules & Terminology
- **Strict Glossary Compliance:** When naming domain concepts (in issue titles, refactor proposals, hypotheses, test names, etc.), always use the precise terms defined in `CONTEXT.md`. Do not drift to synonyms the glossary explicitly avoids.
- **Architectural Respect:** If a proposed solution contradicts an existing ADR (located in `conductor/adr/`), explicitly flag it (e.g., "Contradicts ADR-NNNN, but worth reopening because...") rather than silently overriding it.
