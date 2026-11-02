const OK_PREFIX = 'https://github.com/aniskoubaa/alfaisalx_students_projects/';

/** Only links into the project's own GitHub pages are shown as links. */
export function isUpdatePage(url: unknown): url is string {
  return typeof url === 'string' && url.startsWith(OK_PREFIX);
}
