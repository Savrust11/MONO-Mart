import { TopHeader } from '@/components/TopHeader';
import { TabNav } from '@/components/TabNav';
import { TreeSidebar } from '@/components/TreeSidebar';

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-[#f3f4f6] flex flex-col">
      <TopHeader />
      <TabNav />
      <div className="flex-1 flex min-h-0">
        <TreeSidebar />
        <main className="flex-1 overflow-y-auto">
          {children}
        </main>
      </div>
    </div>
  );
}
