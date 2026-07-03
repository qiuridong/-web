import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ScriptCard } from './ScriptCard';

describe('ScriptCard', () => {
  it('uses container-based sizing so narrow devices scale from the card width', () => {
    render(
      <ScriptCard
        script={{
          slug: 'coklw',
          name: 'COKLW 每日签到',
          description: '容器查询适配测试',
          version: '1.0.0',
          instance_count: 2,
          instance_enabled_count: 1,
          last_run_status: 'success',
          last_run_at: '2026-07-02T01:00:00Z',
          next_run_at: '2026-07-03T01:00:00Z',
          success_rate_7d: 0.98,
        }}
      />,
    );

    const card = screen
      .getByText('COKLW 每日签到')
      .closest('.group');

    expect(card).not.toBeNull();
    expect(card!.className).toContain('[container-type:inline-size]');
    expect(card!.className).toContain('p-[var(--card-pad)]');
    expect(card!.className).toContain('gap-[var(--card-gap)]');
    expect(card!.className).toContain('[--card-pad:clamp(');
    expect(card!.className).toContain('cqw');

    const title = screen.getByText('COKLW 每日签到');
    expect(title.className).toContain('text-[length:var(--card-title)]');

    const footerBadge = screen.getByText('上次成功');
    const footerRow = footerBadge.closest('.mt-auto');
    expect(footerRow).not.toBeNull();
    expect(footerRow!.className).toContain('flex-wrap');
  });
});
