import { Panel } from '../../components/ui';

export const STEPS: readonly string[] = [
  'Select. The robot refuses with a note when a stop file is there, a delivery is running, the program is missing or outside ~/robot_code, or a moving program is chosen while docked (unless it undocks itself).',
  'If the entry asks first, or moves the robot, the screen asks "1 = Yes / 2 = No". A moving program also shows "Robot will move".',
  'The program runs on its own. The screen shows its name and "2 = Stop". Button 2 stops it politely first and forcefully if it keeps running. The same happens at the time limit.',
  'The result screen says Finished, Failed, Stopped or Timed out, with the exit code. Any button returns to the menu, and it returns by itself after 30 seconds.',
];

export function HowItWorks() {
  return (
    <Panel title="What happens when an entry starts">
      <ol className="menu-steps">
        {STEPS.map((s) => (
          <li key={s.slice(0, 12)}>{s}</li>
        ))}
      </ol>
    </Panel>
  );
}
