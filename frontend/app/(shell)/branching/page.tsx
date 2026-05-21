import { BranchStartScreen } from "@/components/branching/BranchStartScreen";

export default function BranchingStartPage() {
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-medium text-foreground">Phân nhánh</h1>
        <p className="text-sm text-muted-foreground">Khởi tạo phiên đọc tương tác</p>
      </header>
      <BranchStartScreen />
    </div>
  );
}
