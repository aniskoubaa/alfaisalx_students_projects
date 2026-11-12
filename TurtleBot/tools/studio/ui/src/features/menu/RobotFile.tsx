import { Button, Panel } from '../../components/ui';
import type { MenuGetAnswer } from '../../api';

export const CHECKER_MISSING_TEXT =
  'The robot does not have the menu checker yet. Deploy the delivery package (delivery/tools/deploy.py) before saving a menu.';

/** What the robot says about its current menu file: no checker, no file, or a file that is not valid. */
export function RobotFileNotice({
  robot,
  blocked,
  onStartStandard,
}: {
  robot: MenuGetAnswer;
  blocked: boolean;
  onStartStandard: () => void;
}) {
  return (
    <>
      {!robot.checker_ok ? (
        <p className="mapping-error" role="alert" data-testid="menu-checker-missing">
          {CHECKER_MISSING_TEXT}
        </p>
      ) : null}
      {!robot.exists ? (
        <p className="dim small" role="status" data-testid="menu-no-file">
          The robot shows the standard menu.
        </p>
      ) : null}
      {robot.exists && blocked ? (
        <Panel title="The robot's menu file is not valid">
          <p className="dim small">
            The robot shows the standard menu until the file is fixed. These are the problems it
            found.
          </p>
          <ul className="menu-problems" data-testid="menu-file-errors">
            {(robot.check?.errors ?? []).map((e, i) => (
              <li key={i}>{e}</li>
            ))}
            {robot.check === null ? <li>The checker could not read the file.</li> : null}
          </ul>
          <label className="field-label" htmlFor="menu-current-file">
            The file on the robot (read only)
          </label>
          <textarea
            id="menu-current-file"
            className="input mono menu-yaml"
            readOnly
            rows={8}
            value={robot.text}
          />
          <div>
            <Button variant="primary" onClick={onStartStandard}>
              Start from the standard menu
            </Button>
          </div>
        </Panel>
      ) : null}
    </>
  );
}
