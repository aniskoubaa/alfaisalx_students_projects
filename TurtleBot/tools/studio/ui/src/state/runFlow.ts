import { missingArgsMessage, requiredArgNames, safeExample } from '../lib/requiredArgs';
import { isHelperProgram } from '../lib/motion';
import { runProgram } from './actions';
import { useArgs } from './args';
import { useStudio } from './store';

export interface RunFlowResult {
  started: boolean;
  /** A plain sentence to show next to the box, empty when there is nothing to say. */
  notice: string;
}

/**
 * Run a program from a list, the way the Programs screen does: a program that needs arguments
 * gets a safe example in its box first, and a program that moves the robot asks for confirmation
 * (that part lives in runProgram).
 */
export async function runFromList(name: string): Promise<RunFlowResult> {
  const s = useStudio.getState();
  if (s.conn.state !== 'connected' || isHelperProgram(name, s.catalog)) {
    return { started: false, notice: '' };
  }
  const entry = s.catalog[name];
  const value = useArgs.getState().args[name] ?? '';
  const required = requiredArgNames(entry);
  if (required.length && !value.trim()) {
    const example = safeExample(entry);
    if (example) useArgs.getState().setArgs(name, example);
    return { started: false, notice: missingArgsMessage(name, required, !!example) };
  }
  return { started: await runProgram(name, value), notice: '' };
}
