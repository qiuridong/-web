/**
 * 「导入到管家」按钮 —— 货架公共仓库版：
 * - 已设「我的管家地址」→ 直接跳到访问者自己的管家 /scripts?import=<bundle>
 * - 未设 → 点击先弹设置，保存后自动跳转
 */
import * as React from 'react';
import { ImportIcon } from 'lucide-react';

import { managerImportUrl, useManagerUrl } from '@/lib/manager';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { ManagerSettingsDialog } from '@/components/ManagerSettings';

export function ImportToManagerButton({ slug }: { slug: string }) {
  const managerUrl = useManagerUrl();
  const [settingsOpen, setSettingsOpen] = React.useState(false);

  if (managerUrl) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <Button variant="secondary" asChild>
            <a href={managerImportUrl(slug, managerUrl)} target="_blank" rel="noreferrer">
              <ImportIcon />
              导入到管家
            </a>
          </Button>
        </TooltipTrigger>
        <TooltipContent>在你的管家（{managerUrl}）中打开并导入</TooltipContent>
      </Tooltip>
    );
  }

  return (
    <>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button variant="secondary" onClick={() => setSettingsOpen(true)}>
            <ImportIcon />
            导入到管家
          </Button>
        </TooltipTrigger>
        <TooltipContent>先设置你自己的管家地址，再一键导入</TooltipContent>
      </Tooltip>
      <ManagerSettingsDialog
        open={settingsOpen}
        onOpenChange={setSettingsOpen}
        afterSave={(url) => window.open(managerImportUrl(slug, url), '_blank', 'noopener')}
      />
    </>
  );
}
