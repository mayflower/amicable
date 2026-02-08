export type TemplateId = "lovable_vite" | "nextjs15" | "fastapi" | "hono" | "remix";

export const TEMPLATES: Array<{
  id: TemplateId;
  title: string;
  description: string;
}> = [
  {
    id: "lovable_vite",
    title: "Lovable Native",
    description: "React 19 + Vite + Tailwind + shadcn/ui",
  },
  {
    id: "nextjs15",
    title: "Production",
    description: "Next.js 15 (App Router) + TypeScript (strict)",
  },
  {
    id: "fastapi",
    title: "AI Agent Backend",
    description: "FastAPI service (Hasura Actions)",
  },
  {
    id: "hono",
    title: "Lightweight Logic",
    description: "Hono + TypeScript (Hasura webhooks)",
  },
  {
    id: "remix",
    title: "Enterprise Dashboard",
    description: "Remix-style (React Router) dashboards",
  },
];

export const templateLabel = (id: string | null | undefined): string => {
  const found = TEMPLATES.find((t) => t.id === id);
  return found ? found.title : "Lovable Native";
};

