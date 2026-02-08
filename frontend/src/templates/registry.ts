export type TemplateId = "lovable_vite" | "nextjs15" | "fastapi" | "hono" | "remix";

export const TEMPLATES: Array<{
  id: TemplateId;
  title: string;
  description: string;
}> = [
  {
    id: "lovable_vite",
    title: "Single-Page App",
    description: "Best for landing pages, dashboards, and client-side apps. React + Vite + Tailwind + shadcn/ui.",
  },
  {
    id: "nextjs15",
    title: "Full-Stack Web App",
    description: "Best for SEO, server rendering, and production sites. Next.js 15 App Router + TypeScript.",
  },
  {
    id: "fastapi",
    title: "Python API",
    description: "Best for data pipelines, ML endpoints, and backend services. FastAPI + Python.",
  },
  {
    id: "hono",
    title: "Lightweight API",
    description: "Best for webhooks, edge functions, and small services. Hono + TypeScript.",
  },
  {
    id: "remix",
    title: "Multi-Page App",
    description: "Best for forms, auth flows, and multi-page apps with server logic. React Router (Remix).",
  },
];

export const templateLabel = (id: string | null | undefined): string => {
  const found = TEMPLATES.find((t) => t.id === id);
  return found ? found.title : "Single-Page App";
};

