import {
  autocompletion,
  closeBrackets,
  closeBracketsKeymap,
  completionKeymap,
} from '@codemirror/autocomplete';
import {
  defaultKeymap,
  history,
  historyKeymap,
  indentWithTab,
  toggleTabFocusMode,
} from '@codemirror/commands';
import { python } from '@codemirror/lang-python';
import {
  HighlightStyle,
  bracketMatching,
  indentOnInput,
  syntaxHighlighting,
} from '@codemirror/language';
import { highlightSelectionMatches, searchKeymap } from '@codemirror/search';
import { Compartment, EditorState } from '@codemirror/state';
import {
  EditorView,
  drawSelection,
  highlightActiveLine,
  highlightActiveLineGutter,
  keymap,
  lineNumbers,
  placeholder,
} from '@codemirror/view';
import { tags as t } from '@lezer/highlight';
import { useEffect, useRef } from 'react';

/** Colours come from CSS variables, so the editor follows the light and dark themes. */
const highlight = HighlightStyle.define([
  {
    tag: [t.keyword, t.operatorKeyword, t.controlKeyword, t.definitionKeyword],
    color: 'var(--code-keyword)',
  },
  { tag: [t.string, t.special(t.string)], color: 'var(--code-string)' },
  { tag: [t.number, t.bool, t.null, t.atom], color: 'var(--code-number)' },
  {
    tag: [t.comment, t.lineComment, t.blockComment],
    color: 'var(--code-comment)',
    fontStyle: 'italic',
  },
  {
    tag: [t.function(t.variableName), t.function(t.propertyName), t.definition(t.variableName)],
    color: 'var(--code-function)',
  },
  { tag: [t.className, t.typeName], color: 'var(--code-type)' },
  { tag: [t.self, t.meta], color: 'var(--code-keyword)' },
  { tag: t.invalid, color: 'var(--code-invalid)' },
]);

const theme = EditorView.theme({
  '&': { height: '100%', color: 'var(--ink)', backgroundColor: 'var(--surface)', fontSize: '13px' },
  '.cm-scroller': { fontFamily: 'var(--font-mono)', lineHeight: '1.55', overflow: 'auto' },
  '.cm-content': { caretColor: 'var(--signal)', padding: '8px 0' },
  '.cm-cursor': { borderLeftColor: 'var(--signal)' },
  '.cm-gutters': {
    backgroundColor: 'var(--surface-2)',
    color: 'var(--muted)',
    border: 'none',
    borderRight: '1px solid var(--line)',
  },
  '.cm-activeLine': { backgroundColor: 'color-mix(in srgb, var(--signal) 6%, transparent)' },
  '.cm-activeLineGutter': {
    backgroundColor: 'color-mix(in srgb, var(--signal) 10%, transparent)',
    color: 'var(--ink)',
  },
  '&.cm-focused': { outline: '2px solid var(--signal)', outlineOffset: '-2px' },
  '.cm-selectionBackground, &.cm-focused > .cm-scroller > .cm-selectionLayer .cm-selectionBackground':
    {
      backgroundColor: 'color-mix(in srgb, var(--signal) 24%, transparent)',
    },
  '.cm-placeholder': { color: 'var(--muted)' },
  '.cm-tooltip': {
    backgroundColor: 'var(--surface)',
    color: 'var(--ink)',
    border: '1px solid var(--line)',
    borderRadius: '6px',
  },
});

export interface CodeEditorProps {
  value: string;
  onChange: (text: string) => void;
  onSave: () => void;
  /** No file open: the editor is empty and cannot be typed in. */
  disabled?: boolean;
  label: string;
  emptyText?: string;
}

export function CodeEditor({
  value,
  onChange,
  onSave,
  disabled,
  label,
  emptyText,
}: CodeEditorProps) {
  const host = useRef<HTMLDivElement>(null);
  const view = useRef<EditorView | null>(null);
  const editable = useRef(new Compartment());
  const onChangeRef = useRef(onChange);
  const onSaveRef = useRef(onSave);
  useEffect(() => {
    onChangeRef.current = onChange;
    onSaveRef.current = onSave;
  });

  useEffect(() => {
    if (!host.current) return;
    const v = new EditorView({
      parent: host.current,
      state: EditorState.create({
        doc: value,
        extensions: [
          lineNumbers(),
          highlightActiveLineGutter(),
          highlightActiveLine(),
          history(),
          drawSelection(),
          EditorView.lineWrapping,
          indentOnInput(),
          bracketMatching(),
          closeBrackets(),
          autocompletion(),
          highlightSelectionMatches(),
          python(),
          syntaxHighlighting(highlight),
          theme,
          placeholder(emptyText ?? ''),
          EditorState.tabSize.of(4),
          EditorView.contentAttributes.of({ 'aria-label': label, spellcheck: 'false' }),
          editable.current.of([
            EditorView.editable.of(!disabled),
            EditorState.readOnly.of(!!disabled),
          ]),
          keymap.of([
            {
              key: 'Mod-s',
              preventDefault: true,
              run: () => {
                onSaveRef.current();
                return true;
              },
            },
            { key: 'Ctrl-m', mac: 'Shift-Alt-m', run: toggleTabFocusMode },
            indentWithTab,
            ...closeBracketsKeymap,
            ...completionKeymap,
            ...searchKeymap,
            ...historyKeymap,
            ...defaultKeymap,
          ]),
          EditorView.updateListener.of((u) => {
            if (u.docChanged) onChangeRef.current(u.state.doc.toString());
          }),
        ],
      }),
    });
    view.current = v;
    return () => {
      v.destroy();
      view.current = null;
    };
    // The editor is created once. Later changes of value and disabled are applied below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const v = view.current;
    if (!v) return;
    const cur = v.state.doc.toString();
    if (cur !== value) {
      v.dispatch({ changes: { from: 0, to: cur.length, insert: value }, selection: { anchor: 0 } });
    }
  }, [value]);

  useEffect(() => {
    view.current?.dispatch({
      effects: editable.current.reconfigure([
        EditorView.editable.of(!disabled),
        EditorState.readOnly.of(!!disabled),
      ]),
    });
  }, [disabled]);

  return <div ref={host} className={'code-editor' + (disabled ? ' is-disabled' : '')} />;
}
