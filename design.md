# Design — Tueka Dashboard

Locked multi-page design system. `tokens.css` is canonical; page-specific raw colours and fonts are not permitted.

## System
- Genre · modern-minimal operations workbench
- Macrostructure · Workbench
- Navigation · persistent application rail + visible N13 command search
- Theme · custom variants: Precision / Community / Atmosphere
- Axes · light or dark tinted paper / geometric sans / restrained cool accent
- Typography · Space Grotesk display · Noto Sans JP body · Geist Mono identifiers
- Icons · Lucide only

## Interaction
- Every mutation uses an explicit Save or confirmation action.
- Motion communicates overlays and state changes only; 120–240 ms exponential easing.
- Reduced motion removes spatial transitions and keeps ≤150 ms opacity changes.
- Focus is immediate, 2 px, and never animated. Touch targets are at least 44 px.
- Reversible rule edits are staged until Save. Ban and Lockdown require typed confirmation.

## Layout
- Mobile-first at 320 / 375 / 414 / 768 px; content breakpoints at 40 / 60 / 90 rem.
- One containment boundary per region; no card-in-card or equal three-card feature grids.
- Desktop uses an asymmetric rail/content workbench. Mobile uses a top bar and full-height navigation sheet.
- Moderation rule editing is a four-step task flow, never a single field wall.

## Voice
- Japanese is concise and formal; English is a complete peer locale.
- Labels name the object; buttons use a specific verb; errors state what happened and how to recover.
- Do not invent metrics, testimonials, protection claims, or Discord state.

## Exports
- Canonical CSS · `tokens.css`
- Tailwind v4 · map canonical names directly in `@theme`; the application does not depend on Tailwind.
- DTCG · map each canonical token to `$value` / `$type` when exporting `tokens.json`.
- shadcn/ui · map paper→background/card, ink→foreground, accent→primary, rule→border; the application does not ship shadcn styling.

## Build and release
- Install and build the SPA from `dashboard/frontend` with `npm install` and `npm run build`.
- Set `DASHBOARD_UI_V2=true` to serve the complete SPA for dashboard routes. Keep it false for the Jinja rollback UI.
- Optionally set `DASHBOARD_UI_V2_GUILDS` to a comma-separated guild ID allowlist during rollout.
- The generated `dist`, dependency tree, and Playwright artifacts are intentionally not tracked.

## Discord permissions
- Lockdown and channel lock require Manage Channels.
- Reaction cleanup and purge require Manage Messages.
- Audit-log actor correlation requires View Audit Log.
- Timeout, Kick, and Ban require their corresponding Discord permissions and still respect role hierarchy at execution time.
