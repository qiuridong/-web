/**
 * <CodeMirrorLazy> — 真正的 CodeMirror 编辑器(被 React.lazy 包住)
 *
 * 为什么单独一个文件:
 *   - @uiw/react-codemirror + @codemirror/* 加起来 ~200KB gz
 *   - 通过 React.lazy 默认 import 让 Vite 拆出独立 chunk(vendor-codemirror)
 *   - 只有用户真打开"编辑文件"Dialog 才下载
 *
 * 父组件 FileEditDialog 用法:
 *   const CodeMirror = React.lazy(() => import('./CodeMirrorLazy'));
 *   <Suspense fallback={<Skeleton/>}>
 *     <CodeMirror value={...} onChange={...} language="python" readOnly={false}/>
 *   </Suspense>
 */
import CodeMirror, { type ReactCodeMirrorRef } from '@uiw/react-codemirror';
import { python } from '@codemirror/lang-python';
import { yaml } from '@codemirror/lang-yaml';
import type { Extension } from '@codemirror/state';
import { EditorView, keymap } from '@codemirror/view';
import type { KeyBinding } from '@codemirror/view';
import { useEffect, useMemo, useRef } from 'react';

import type { Language } from './fileLanguage';

export interface CodeMirrorLazyProps {
  value: string;
  onChange?: (next: string) => void;
  language: Language;
  readOnly?: boolean;
  /** Ctrl+S / Cmd+S 触发,返回 true 阻止默认浏览器保存对话框 */
  onSave?: () => void;
  /** 主题(light/dark 跟随父级),@uiw/react-codemirror 默认会用 system dark */
  className?: string;
}

function pickLangExtension(lang: Language): Extension[] {
  switch (lang) {
    case 'python':
      return [python()];
    case 'yaml':
      return [yaml()];
    default:
      return [];
  }
}

export default function CodeMirrorLazy({
  value,
  onChange,
  language,
  readOnly = false,
  onSave,
  className,
}: CodeMirrorLazyProps) {
  const ref = useRef<ReactCodeMirrorRef>(null);

  // Ctrl+S / Cmd+S 拦截
  const saveKeymap: Extension = useMemo(() => {
    if (!onSave) return [];
    const binding: KeyBinding = {
      key: 'Mod-s',
      run: () => {
        onSave();
        return true; // 阻止默认
      },
    };
    return keymap.of([binding]);
  }, [onSave]);

  // 让编辑器自适应高度 + 滚动
  const fixedHeightTheme: Extension = useMemo(
    () =>
      EditorView.theme({
        '&': {
          height: '100%',
          minHeight: '320px',
          maxHeight: '60vh',
          fontSize: '13px',
        },
        '.cm-scroller': { fontFamily: 'var(--font-mono, JetBrains Mono, monospace)' },
      }),
    [],
  );

  const extensions: Extension[] = useMemo(
    () => [...pickLangExtension(language), saveKeymap, fixedHeightTheme],
    [language, saveKeymap, fixedHeightTheme],
  );

  // 当 readOnly 切换时 CodeMirror 不会自动重建,在 effect 里 reconfigure。
  // 这里我们直接通过 prop 受控,@uiw/react-codemirror 会处理 readOnly 切换。
  useEffect(() => {
    // 用户进 Dialog 后聚焦到编辑器,体验更顺
    if (!readOnly) {
      ref.current?.view?.focus();
    }
  }, [readOnly]);

  return (
    <CodeMirror
      ref={ref}
      value={value}
      onChange={onChange}
      readOnly={readOnly}
      extensions={extensions}
      basicSetup={{
        lineNumbers: true,
        foldGutter: true,
        searchKeymap: true,
        highlightActiveLine: !readOnly,
        highlightActiveLineGutter: !readOnly,
        autocompletion: false, // 不要补全,避免和 Ctrl+Space 等冲突
      }}
      className={className}
      // 让 @uiw/react-codemirror 走 light/dark 跟随 :root.dark
      theme={
        typeof document !== 'undefined' && document.documentElement.classList.contains('dark')
          ? 'dark'
          : 'light'
      }
    />
  );
}
