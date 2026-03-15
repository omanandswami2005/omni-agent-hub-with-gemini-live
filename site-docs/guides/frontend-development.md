# Frontend Development

Guide for contributing to the Omni dashboard.

## Stack

- **React 19** (JavaScript, not TypeScript)
- **Vite 6** for bundling
- **Tailwind CSS 4** for styling
- **shadcn/ui** for UI components
- **Zustand 5** for state management

## Development

```bash
cd dashboard
pnpm install
pnpm dev
```

## Component Organization

```
src/components/
├── layout/     # Sidebar, header, app shell
├── chat/       # Message list, input, audio controls
├── genui/      # GenUI renderer and component registry
├── persona/    # Persona selector and editor
├── mcp/        # Plugin store and management
├── clients/    # Connected device viewer
├── session/    # Session history
├── sandbox/    # E2B desktop viewer + file upload
├── auth/       # Login, signup, auth guard
├── shared/     # Reusable components
└── ui/         # shadcn/ui primitives
```

## Conventions

- **No TypeScript** — All files are `.jsx`
- **Zustand for state** — No Redux, no Context for global state
- **shadcn/ui** — Install new components via `pnpm dlx shadcn@latest add <component>`
- **Tailwind** — Use utility classes, avoid custom CSS
- **pnpm** — Always use pnpm, never npm or yarn
