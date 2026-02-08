// Monaco needs explicit worker wiring under Vite.
// This keeps @monaco-editor/react working without a plugin.

// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore
import EditorWorker from "monaco-editor/esm/vs/editor/editor.worker?worker";
// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore
import JsonWorker from "monaco-editor/esm/vs/language/json/json.worker?worker";
// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore
import CssWorker from "monaco-editor/esm/vs/language/css/css.worker?worker";
// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore
import HtmlWorker from "monaco-editor/esm/vs/language/html/html.worker?worker";
// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore
import TsWorker from "monaco-editor/esm/vs/language/typescript/ts.worker?worker";

type MonacoEnvironment = {
  getWorker: (moduleId: unknown, label: string) => Worker;
};

const globalScope = self as unknown as { MonacoEnvironment?: MonacoEnvironment };

globalScope.MonacoEnvironment = {
  getWorker(_: unknown, label: string) {
    if (label === "json") return new JsonWorker();
    if (label === "css" || label === "scss" || label === "less") return new CssWorker();
    if (label === "html" || label === "handlebars" || label === "razor") return new HtmlWorker();
    if (label === "typescript" || label === "javascript") return new TsWorker();
    return new EditorWorker();
  },
};
