/**
 * useDebounce — 通用 debounce hook
 *
 * 用于把搜索框输入降频,避免每次 keystroke 都打 API。
 *
 * 用法:
 *   const [raw, setRaw] = useState('');
 *   const debounced = useDebounce(raw, 250);
 *   // 把 debounced 作为 query filter
 */
import { useEffect, useState } from 'react';

export function useDebounce<T>(value: T, delayMs = 250): T {
  const [debounced, setDebounced] = useState<T>(value);

  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(id);
  }, [value, delayMs]);

  return debounced;
}

export default useDebounce;
