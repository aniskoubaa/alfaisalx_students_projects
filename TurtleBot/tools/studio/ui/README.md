# TurtleBot Studio 2.0 interface

React 18 + TypeScript (strict) + Vite. Only people who change the interface need Node. Students use the
built files in `../web/v2/`, which are committed.

## Commands

```
npm ci            # install the pinned versions from package-lock.json
npm run dev       # dev server at http://localhost:5173/v2/?token=<token>
npm run lint
npm run typecheck
npm test
npm run build     # writes ../web/v2/ (the folder is emptied first)
```

## Dev server

Start Studio with a fake robot, then the dev server. `/api` is proxied to port 8790
(see `vite.config.ts`):

```
python studio.py --fake --no-browser --stay-open --port 8790
```

Open `http://localhost:5173/v2/?token=` followed by the token Studio prints.

To use another Studio port or dev-server port (for example when two people work in `ui/`), set
`STUDIO_PORT` and `DEV_PORT` before `npm run dev`. Use a scratch `STUDIO_CONFIG_DIR` for the fake
Studio so your real settings stay untouched.

## Layout of `src/`

- `api/` typed client (`client.ts`), typed event stream with reconnect (`sse.ts`), and `types.ts`
  for every endpoint and event.
- `state/` zustand stores: `store.ts` (fed by the event stream), `selectors.ts`, `ui.ts` (theme, menu),
  `feedback.ts` (toasts and the confirm and inform dialogs), `code.ts` (editor text), `actions.tsx`
  and `codeActions.tsx` (everything that calls Studio), `router.ts`, `runtime.ts`.
- `components/ui/` design system primitives. `components/shell/` top bar, menu, banners, E-STOP.
- `screens/` Overview, Programs, Code, Files, and the placeholder for later screens.
- `styles/` tokens (light and dark), base, primitives, shell, screens.
