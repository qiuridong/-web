import { ThemeProvider as NextThemesProvider } from 'next-themes';

/** 深色一等公民:默认 dark,允许用户切换并记忆。 */
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  return (
    <NextThemesProvider attribute="class" defaultTheme="dark" enableSystem={false} storageKey="shelf-theme">
      {children}
    </NextThemesProvider>
  );
}
