import { basicSetup } from "codemirror";
import { indentWithTab } from "@codemirror/commands";
import { python } from "@codemirror/lang-python";
import { HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import {
  Decoration,
  EditorView,
  MatchDecorator,
  ViewPlugin,
  keymap,
} from "@codemirror/view";
import { tags } from "@lezer/highlight";

const placeholderMatcher = new MatchDecorator({
  regexp: /\$\{\s*(?:model|model_provider|api_key|base_url|system_prompt|human_message)\s*\}/g,
  decoration: Decoration.mark({ class: "cm-template-placeholder" }),
});

const placeholderHighlighter = ViewPlugin.fromClass(
  class {
    constructor(view) {
      this.decorations = placeholderMatcher.createDeco(view);
    }

    update(update) {
      this.decorations = placeholderMatcher.updateDeco(update, this.decorations);
    }
  },
  { decorations: (plugin) => plugin.decorations },
);

const pythonHighlightStyle = HighlightStyle.define([
  { tag: tags.keyword, color: "#c792ea" },
  { tag: [tags.name, tags.variableName], color: "#e5e7eb" },
  { tag: [tags.function(tags.variableName), tags.definition(tags.variableName)], color: "#82aaff" },
  { tag: [tags.string, tags.special(tags.string)], color: "#c3e88d" },
  { tag: [tags.number, tags.bool, tags.null], color: "#f78c6c" },
  { tag: [tags.comment, tags.docComment], color: "#7f8c98", fontStyle: "italic" },
  { tag: [tags.operator, tags.punctuation], color: "#89ddff" },
  { tag: [tags.className, tags.typeName], color: "#ffcb6b" },
  { tag: tags.propertyName, color: "#f07178" },
]);

const editorTheme = EditorView.theme(
  {
    "&": {
      height: "100%",
      minHeight: "200px",
      backgroundColor: "#0b1020",
      color: "#e5e7eb",
      fontSize: "13px",
    },
    ".cm-scroller": {
      overflow: "auto",
      fontFamily: 'Consolas, "SFMono-Regular", Menlo, monospace',
      lineHeight: "1.55",
    },
    ".cm-content": {
      padding: "12px 0",
      caretColor: "#ffffff",
    },
    ".cm-line": { padding: "0 12px" },
    ".cm-gutters": {
      backgroundColor: "#111827",
      color: "#64748b",
      borderRight: "1px solid #263244",
    },
    ".cm-activeLineGutter": { backgroundColor: "#1d2940", color: "#cbd5e1" },
    ".cm-activeLine": { backgroundColor: "rgba(59, 130, 246, 0.08)" },
    ".cm-selectionBackground, &.cm-focused .cm-selectionBackground": {
      backgroundColor: "rgba(59, 130, 246, 0.34) !important",
    },
    ".cm-cursor, .cm-dropCursor": { borderLeftColor: "#ffffff" },
    ".cm-matchingBracket": {
      backgroundColor: "rgba(34, 197, 94, 0.2)",
      outline: "1px solid #22c55e",
    },
    ".cm-template-placeholder": {
      color: "#ffcb6b",
      backgroundColor: "rgba(245, 158, 11, 0.13)",
      borderRadius: "3px",
      fontWeight: "700",
    },
    ".cm-tooltip": { border: "1px solid #334155", backgroundColor: "#111827" },
    ".cm-tooltip-autocomplete > ul > li[aria-selected]": { backgroundColor: "#1d4ed8" },
  },
  { dark: true },
);

function create(parent, initialValue) {
  const view = new EditorView({
    doc: initialValue || "",
    parent,
    extensions: [
      basicSetup,
      keymap.of([indentWithTab]),
      python(),
      syntaxHighlighting(pythonHighlightStyle),
      placeholderHighlighter,
      editorTheme,
    ],
  });

  return {
    getValue() {
      return view.state.doc.toString();
    },
    setValue(value) {
      view.dispatch({
        changes: { from: 0, to: view.state.doc.length, insert: value || "" },
      });
    },
    focus() {
      view.focus();
    },
    destroy() {
      view.destroy();
    },
    view,
  };
}

window.PythonCodeEditor = { create };
