import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router';
import { describe, expect, it, vi } from 'vitest';

import { ScriptDetail } from './ScriptDetail';

vi.mock('@/components/common/PageHeader', () => ({
  default: ({ title, description }: { title: string; description?: string }) => (
    <header>
      <h1>{title}</h1>
      {description ? <p>{description}</p> : null}
    </header>
  ),
}));

vi.mock('@/components/common/EmptyState', () => ({
  default: ({ title, description }: { title: string; description?: string }) => (
    <div>
      <p>{title}</p>
      {description ? <p>{description}</p> : null}
    </div>
  ),
}));

vi.mock('@/components/common/InstancesPanel', () => ({
  default: () => <div>instances-panel</div>,
}));

vi.mock('@/components/common/LogViewer', () => ({
  default: () => <div>log-viewer</div>,
}));

vi.mock('@/components/common/RunsPanel', () => ({
  default: () => <div>runs-panel</div>,
}));

vi.mock('./components/FileEditDialog', () => ({
  default: () => null,
}));

vi.mock('./components/ScriptFileList', () => ({
  default: () => <div>script-file-list</div>,
}));

const mockScript = {
  slug: 'coklw',
  name: 'COKLW 每日签到',
  description: 'README 防溢出回归',
  version: '1.0.0',
  enabled: true,
  author: 'tester',
  homepage: 'https://example.com',
  instance_count: 1,
  default_cron: '0 9 * * *',
  default_timeout_sec: 3600,
  requirements_present: true,
  fields_schema: [],
  runtime: null,
  last_scanned_at: '2026-07-02T00:00:00Z',
  next_run_at: '2026-07-03T00:00:00Z',
  last_run_at: '2026-07-02T00:00:00Z',
  readme_md: [
    '| key | value |',
    '| --- | --- |',
    `| cookie | ${'x'.repeat(120)} |`,
    '',
    `inline code: \`wordpress_logged_in_${'x'.repeat(80)}\``,
    '',
    '```powershell',
    `$env:COKLW_COOKIE = "${'x'.repeat(120)}"`,
    '```',
  ].join('\n'),
};

vi.mock('@/api/hooks/scripts', () => ({
  useScript: () => ({
    data: mockScript,
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  }),
  useScanScripts: () => ({ mutate: vi.fn(), isPending: false }),
  useEnableScript: () => ({ mutate: vi.fn(), isPending: false }),
  useDisableScript: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock('@/api/hooks/runs', () => ({
  useRuns: () => ({ data: [] }),
}));

describe('ScriptDetail README tab', () => {
  it('makes the whole README one horizontal scroller (整段横滑) rather than per-block scrollers', async () => {
    const user = userEvent.setup();
    const { container } = render(
      <MemoryRouter initialEntries={['/scripts/coklw']}>
        <Routes>
          <Route path="/scripts/:slug" element={<ScriptDetail />} />
        </Routes>
      </MemoryRouter>,
    );

    await user.click(screen.getByRole('tab', { name: 'README' }));

    // 单一滚动区 = 承载全部 markdown 的 <article>,超宽内容在此整段横滑
    const article = container.querySelector('article');
    expect(article).not.toBeNull();
    expect(article!.className).toContain('overflow-x-auto');

    // 表格保持完整宽度、不被裁剪;直接坐落在 article 里,没有自己的局部滚动 div
    const table = screen.getByRole('table');
    expect(table.className).toContain('min-w-max');
    expect(table.closest('.overflow-x-auto')).toBe(article);
    expect(table.parentElement).toBe(article);

    const inlineCode = screen.getByText((content) =>
      content.includes('wordpress_logged_in_'),
    );
    expect(inlineCode.tagName).toBe('CODE');
    expect(inlineCode.className).toContain('break-all');
    expect(inlineCode.className).toContain('whitespace-normal');

    // 代码块同样保持完整宽度,直接坐落在 article 里,横滑归属同一个滚动区
    const pre = container.querySelector('pre');
    expect(pre).not.toBeNull();
    expect(pre!.className).toContain('min-w-max');
    expect(pre!.closest('.overflow-x-auto')).toBe(article);
    expect(pre!.parentElement).toBe(article);
  });
});
