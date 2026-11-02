/**
 * Split an arguments box the way a shell would: spaces separate, quotes group,
 * a backslash escapes the next character. Throws a plain message on an open quote.
 */
const BACKSLASH = String.fromCharCode(92);

export function splitArgs(s: string): string[] {
  const out: string[] = [];
  let cur = '';
  let q: string | null = null;
  let has = false;
  for (let i = 0; i < s.length; i++) {
    const c = s.charAt(i);
    if (q) {
      if (c === q) q = null;
      else if (
        c === BACKSLASH &&
        q === '"' &&
        i + 1 < s.length &&
        ('"' + BACKSLASH).includes(s.charAt(i + 1))
      ) {
        cur += s.charAt(++i);
      } else cur += c;
    } else if (c === '"' || c === "'") {
      q = c;
      has = true;
    } else if (/\s/.test(c)) {
      if (cur || has) {
        out.push(cur);
        cur = '';
        has = false;
      }
    } else if (c === BACKSLASH && i + 1 < s.length) cur += s.charAt(++i);
    else cur += c;
  }
  if (q) throw new Error('Unclosed quote in the arguments.');
  if (cur || has) out.push(cur);
  return out;
}
