import { classicHref } from '../lib/classic';
import { EmptyState } from '../components/ui';
import type { RouteDef } from '../state/router';

/** Placeholder for screens that arrive in a later build, so the menu is complete. */
export function ComingSoon({ route }: { route: RouteDef }) {
  const Icon = route.icon;
  return (
    <div className="page">
      <h1 className="page-title">{route.label}</h1>
      <div className="panel">
        <EmptyState icon={<Icon size={32} />} title="Coming in this build">
          {route.blurb}
          {route.classic ? (
            <>
              {' '}
              Until it arrives here, use the classic Studio:{' '}
              <a href={classicHref(route.classic)}>open {route.label} in the classic Studio</a>.
            </>
          ) : null}
        </EmptyState>
      </div>
    </div>
  );
}
