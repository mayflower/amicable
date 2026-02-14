export type TemplateId =
  | "vite"
  | "nextjs15"
  | "fastapi"
  | "hono"
  | "remix"
  | "nuxt3"
  | "sveltekit"
  | "laravel"
  | "flutter"
  | "phoenix"
  | "aspnetcore"
  | "quarkus";

export const TEMPLATES: Array<{
  id: TemplateId;
  title: string;
  description: string;
}> = [
  {
    id: "vite",
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
  {
    id: "nuxt3",
    title: "Vue Full-Stack App",
    description: "Best for teams preferring Vue and Nuxt conventions. Nuxt 3 + Vite.",
  },
  {
    id: "sveltekit",
    title: "SvelteKit Full-Stack App",
    description: "Best for fast iteration and small-to-medium full-stack apps. SvelteKit + Vite.",
  },
  {
    id: "laravel",
    title: "Laravel Full-Stack App",
    description: "Best for PHP ecosystems and traditional MVC apps. Laravel + PHP.",
  },
  {
    id: "flutter",
    title: "Flutter Mobile App (Web-First)",
    description:
      "Best for cross-platform mobile apps with fast web preview iteration. Flutter + Dart.",
  },
  {
    id: "phoenix",
    title: "Phoenix Full-Stack App",
    description:
      "Best for Elixir teams that want LiveView-first development and fast code reloading. Phoenix + Elixir.",
  },
  {
    id: "aspnetcore",
    title: "ASP.NET Core Web App",
    description:
      "Best for C# teams that need enterprise APIs and robust tooling. ASP.NET Core + dotnet watch.",
  },
  {
    id: "quarkus",
    title: "Quarkus Full-Stack App",
    description:
      "Best for Java teams wanting fast startup and productive dev mode. Quarkus + Maven dev mode.",
  },
];

export const templateLabel = (id: string | null | undefined): string => {
  const found = TEMPLATES.find((t) => t.id === id);
  return found ? found.title : "Single-Page App";
};
