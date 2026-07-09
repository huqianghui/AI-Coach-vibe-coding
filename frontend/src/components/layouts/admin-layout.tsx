import { useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { LucideIcon } from "lucide-react";
import {
  LayoutDashboard,
  Users,
  UserCircle,
  BookOpen,
  ClipboardCheck,
  FileText,
  Lightbulb,
  Wand2,
  MessageSquare,
  BarChart,
  Cloud,
  Radio,
  Settings,
  ChevronLeft,
  ChevronRight,
  Menu,
  LogOut,
} from "lucide-react";
import {
  Button,
  Avatar,
  AvatarFallback,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Separator,
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui";
import { LanguageSwitcher } from "@/components/shared/language-switcher";
import { ThemePicker } from "@/components/shared/theme-picker";
import { Breadcrumb } from "@/components/shared/breadcrumb";
import { PageTransition } from "@/components/shared/page-transition";
import { useAuthStore } from "@/stores/auth-store";
import { useLogout } from "@/hooks/use-auth";
import { cn } from "@/lib/utils";

interface SidebarGroup {
  labelKey: string;
  items: Array<{ path: string; labelKey: string; icon: LucideIcon }>;
}

const sidebarGroups: SidebarGroup[] = [
  {
    labelKey: "configuration",
    items: [
      { path: "/admin/azure-config", labelKey: "azureServices", icon: Cloud },
      { path: "/admin/voice-live", labelKey: "voiceLive", icon: Radio },
      { path: "/admin/meta-skills", labelKey: "metaSkills", icon: Wand2 },
      { path: "/admin/settings", labelKey: "settings", icon: Settings },
    ],
  },
  {
    labelKey: "content",
    items: [
      { path: "/admin/hcp-profiles", labelKey: "hcpProfiles", icon: UserCircle },
      { path: "/admin/scenarios", labelKey: "scenarios", icon: BookOpen },
      { path: "/admin/scoring-rubrics", labelKey: "scoringRubrics", icon: ClipboardCheck },
      { path: "/admin/materials", labelKey: "materials", icon: FileText },
      { path: "/admin/skills", labelKey: "skillHub", icon: Lightbulb },
      { path: "/admin/prompts", labelKey: "prompts", icon: MessageSquare },
    ],
  },
  {
    labelKey: "analytics",
    items: [
      { path: "/admin/dashboard", labelKey: "dashboard", icon: LayoutDashboard },
      { path: "/admin/reports", labelKey: "reports", icon: BarChart },
      { path: "/admin/users", labelKey: "users", icon: Users },
    ],
  },
];

function SidebarNavItem({
  item,
  collapsed,
  isActive,
  onClick,
}: {
  item: { path: string; labelKey: string; icon: LucideIcon };
  collapsed: boolean;
  isActive: boolean;
  onClick?: () => void;
}) {
  const { t } = useTranslation("nav");
  const Icon = item.icon;

  const link = (
    <NavLink
      to={item.path}
      onClick={onClick}
      className={cn(
        "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors duration-150",
        isActive
          ? "bg-sidebar-primary/10 text-sidebar-primary border-l-[3px] border-sidebar-primary font-medium"
          : "text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-foreground border-l-[3px] border-transparent"
      )}
    >
      <Icon className="size-5 shrink-0" />
      {!collapsed && <span>{t(item.labelKey)}</span>}
    </NavLink>
  );

  if (collapsed) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>{link}</TooltipTrigger>
        <TooltipContent side="right">{t(item.labelKey)}</TooltipContent>
      </Tooltip>
    );
  }

  return link;
}

export function AdminLayout() {
  const { t: tNav } = useTranslation("nav");
  const { t: tCommon } = useTranslation("common");
  const { user } = useAuthStore();
  const logout = useLogout();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const userInitials = user?.full_name
    ? user.full_name
        .split(" ")
        .map((n) => n[0])
        .join("")
        .toUpperCase()
        .slice(0, 2)
    : "A";

  return (
    <TooltipProvider delayDuration={0}>
      <div className="flex min-h-screen">
        {/* Desktop sidebar */}
        <aside
          className={cn(
            "hidden flex-col border-r bg-sidebar text-sidebar-foreground transition-all duration-300 md:flex",
            collapsed ? "w-16" : "w-60"
          )}
        >
          {/* Sidebar header */}
          <div className="flex h-14 items-center gap-2 border-b border-sidebar-border px-3">
            <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5"/><path d="M9 18h6"/><path d="M10 22h4"/></svg>
            </div>
            {!collapsed && (
              <span className="font-semibold text-sidebar-foreground">
                AI Coach Admin
              </span>
            )}
          </div>

          {/* Sidebar nav — grouped */}
          <nav className="flex-1 overflow-y-auto p-2">
            {sidebarGroups.map((group, groupIdx) => (
              <div key={group.labelKey}>
                {collapsed ? (
                  groupIdx > 0 && <Separator className="my-2 bg-sidebar-foreground/10" />
                ) : (
                  <div
                    className={cn(
                      "mb-1 px-3 text-[11px] font-medium uppercase tracking-wider text-sidebar-foreground/40",
                      groupIdx > 0 ? "mt-4" : "mt-2"
                    )}
                  >
                    {tNav(group.labelKey)}
                  </div>
                )}
                <div className="space-y-0.5">
                  {group.items.map((item) => (
                    <SidebarNavItem
                      key={item.path}
                      item={item}
                      collapsed={collapsed}
                      isActive={location.pathname === item.path}
                    />
                  ))}
                </div>
              </div>
            ))}
          </nav>

          {/* Collapse toggle */}
          <div className="border-t border-sidebar-border p-2">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setCollapsed(!collapsed)}
              className="w-full text-sidebar-foreground/70 hover:bg-sidebar-primary/10 hover:text-sidebar-foreground"
            >
              {collapsed ? (
                <ChevronRight className="size-5" />
              ) : (
                <ChevronLeft className="size-5" />
              )}
            </Button>
          </div>
        </aside>

        {/* Mobile sidebar sheet */}
        <Sheet open={mobileMenuOpen} onOpenChange={setMobileMenuOpen}>
          <SheetContent
            side="left"
            className="w-60 p-0 bg-sidebar text-sidebar-foreground"
          >
            <SheetHeader className="border-b border-sidebar-border px-3 py-4">
              <SheetTitle className="text-sidebar-foreground">AI Coach Admin</SheetTitle>
            </SheetHeader>
            <nav className="p-2">
              {sidebarGroups.map((group, groupIdx) => (
                <div key={group.labelKey}>
                  <div
                    className={cn(
                      "mb-1 px-3 text-[11px] font-medium uppercase tracking-wider text-sidebar-foreground/40",
                      groupIdx > 0 ? "mt-4" : "mt-2"
                    )}
                  >
                    {tNav(group.labelKey)}
                  </div>
                  <div className="space-y-0.5">
                    {group.items.map((item) => (
                      <SidebarNavItem
                        key={item.path}
                        item={item}
                        collapsed={false}
                        isActive={location.pathname === item.path}
                        onClick={() => setMobileMenuOpen(false)}
                      />
                    ))}
                  </div>
                </div>
              ))}
            </nav>
          </SheetContent>
        </Sheet>

        {/* Main content area */}
        <div className="flex flex-1 flex-col">
          {/* Top bar */}
          <header className="sticky top-0 z-40 flex h-14 items-center border-b bg-background px-4">
            {/* Mobile hamburger */}
            <Button
              variant="ghost"
              size="icon"
              className="md:hidden"
              onClick={() => setMobileMenuOpen(true)}
            >
              <Menu className="size-5" />
            </Button>

            {/* Breadcrumb */}
            <Breadcrumb />

            {/* Right side */}
            <div className="ml-auto flex items-center gap-2">
              <ThemePicker />
              <LanguageSwitcher />
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="ghost"
                    className="flex items-center gap-2 px-2"
                  >
                    <Avatar className="size-8">
                      <AvatarFallback className="text-xs">
                        {userInitials}
                      </AvatarFallback>
                    </Avatar>
                    <span className="hidden text-sm md:inline">
                      {user?.full_name}
                    </span>
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-48">
                  <DropdownMenuItem>{tCommon("profile")}</DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={logout}>
                    <LogOut className="size-4" />
                    {tCommon("logout")}
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </header>

          {/* Page content */}
          <main className="flex-1 bg-muted p-4 lg:p-6">
            <PageTransition />
          </main>
        </div>
      </div>
    </TooltipProvider>
  );
}
