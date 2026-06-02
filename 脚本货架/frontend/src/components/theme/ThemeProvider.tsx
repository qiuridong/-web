import { ThemeProvider as NextThemesProvider } from 'next-themes';

/** 深色一等公民:默认 dark,允许用户切换(浅色 / 深色 / 跟随系统)并记忆。 */
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  return (
    <NextThemesProvider attribute="class" defaultTheme="dark" enableSystem storageKey="shelf-theme">
      {children}
    </NextThemesProvider>
  );
}
