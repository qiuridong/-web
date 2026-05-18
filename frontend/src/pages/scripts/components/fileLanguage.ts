/**
 * 文件路径 → CodeMirror 语言模式的轻量推断函数。
 *
 * 单独成文件,让 FileEditDialog 可以静态 import 它(不会把 CodeMirror 主体拖进主 bundle)。
 * CodeMirror 本体由 CodeMirrorLazy.tsx 通过 React.lazy 异步加载。
 */
export type Language = 'python' | 'yaml' | 'plain';

export function inferLanguageFromPath(path: string): Language {
  const lower = path.toLowerCase();
  if (lower.endsWith('.py')) return 'python';
  if (lower.endsWith('.yaml') || lower.endsWith('.yml')) return 'yaml';
  return 'plain';
}
