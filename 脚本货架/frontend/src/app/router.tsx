import { createBrowserRouter } from 'react-router-dom';

import { AppLayout } from '@/components/AppLayout';
import { GalleryPage } from '@/pages/GalleryPage';
import { DetailPage } from '@/pages/DetailPage';
import { SettingsPage } from '@/pages/SettingsPage';
import { NotFoundPage } from '@/pages/NotFoundPage';

export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [
      { path: '/', element: <GalleryPage /> },
      { path: '/scripts/:slug', element: <DetailPage /> },
      { path: '/settings', element: <SettingsPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]);
