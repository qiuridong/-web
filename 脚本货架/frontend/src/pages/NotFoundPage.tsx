import { Link } from 'react-router-dom';

import { Button } from '@/components/ui/button';

export function NotFoundPage() {
  return (
    <div className="flex flex-col items-center justify-center gap-4 py-24 text-center">
      <p className="text-5xl font-bold tracking-tight text-muted-foreground/40">404</p>
      <p className="text-muted-foreground">页面不存在</p>
      <Button asChild variant="outline">
        <Link to="/">返回画廊</Link>
      </Button>
    </div>
  );
}
