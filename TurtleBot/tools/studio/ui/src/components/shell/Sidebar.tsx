import { PanelLeftClose, PanelLeftOpen, Power } from 'lucide-react';
import { quitStudio } from '../../state/actions';
import { useCode } from '../../state/code';
import { NAV_GROUPS, ROUTES, navigate, useRoute } from '../../state/router';
import { useUi } from '../../state/ui';
import { Tooltip } from '../ui';

export function Sidebar() {
  const route = useRoute();
  const collapsed = useUi((s) => s.navCollapsed);
  const toggleNav = useUi((s) => s.toggleNav);
  const navOpen = useUi((s) => s.navOpen);
  const setNavOpen = useUi((s) => s.setNavOpen);
  const codeDirty = useCode((s) => s.text !== s.orig && s.name !== null);

  return (
    <>
      <nav
        id="sidebar"
        aria-label="Sections"
        className={['sidebar', collapsed ? 'is-collapsed' : '', navOpen ? 'is-open' : '']
          .filter(Boolean)
          .join(' ')}
      >
        <div className="nav-list">
          {NAV_GROUPS.map((g) => (
            <section key={g.id} className="nav-group" aria-labelledby={'nav-h-' + g.id}>
              <h2 className="nav-heading" id={'nav-h-' + g.id}>
                {g.label}
              </h2>
              <ul className="nav-items">
                {ROUTES.filter((r) => r.nav !== false && r.group === g.id).map((r) => {
                  const Icon = r.icon;
                  const active =
                    r.path === route.path || (r.path === '/tools' && route.path === '/settings');
                  const link = (
                    <a
                      href={'#' + r.path}
                      className={'nav-item' + (active ? ' is-active' : '')}
                      aria-current={active ? 'page' : undefined}
                      onClick={(e) => {
                        e.preventDefault();
                        navigate(r.path);
                        setNavOpen(false);
                      }}
                    >
                      <Icon size={18} aria-hidden="true" />
                      <span className="nav-label">{r.label}</span>
                      {r.path === '/code' && codeDirty ? (
                        <span className="nav-dot" role="img" aria-label="unsaved changes" />
                      ) : null}
                    </a>
                  );
                  return (
                    <li key={r.path}>
                      {collapsed ? (
                        <Tooltip content={r.label} side="right">
                          {link}
                        </Tooltip>
                      ) : (
                        link
                      )}
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}
        </div>
        <div className="nav-foot">
          <button
            type="button"
            className="nav-item nav-button"
            onClick={() => void quitStudio()}
            aria-label="Quit Studio"
            title="Quit Studio"
          >
            <Power size={18} aria-hidden="true" />
            <span className="nav-label">Quit Studio</span>
          </button>
          <button
            type="button"
            className="nav-item nav-button nav-collapse"
            onClick={toggleNav}
            aria-label={collapsed ? 'Expand the menu' : 'Collapse the menu'}
            title={collapsed ? 'Expand the menu' : 'Collapse the menu'}
            aria-pressed={collapsed}
          >
            {collapsed ? (
              <PanelLeftOpen size={18} aria-hidden="true" />
            ) : (
              <PanelLeftClose size={18} aria-hidden="true" />
            )}
            <span className="nav-label">Collapse menu</span>
          </button>
        </div>
      </nav>
      {navOpen ? (
        <button
          type="button"
          className="nav-scrim"
          aria-label="Close menu"
          onClick={() => setNavOpen(false)}
        />
      ) : null}
    </>
  );
}
