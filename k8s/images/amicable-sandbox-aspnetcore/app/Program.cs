var builder = WebApplication.CreateBuilder(args);
var app = builder.Build();

app.MapGet("/healthz", () => Results.Json(new { status = "ok" }));

app.MapGet("/", () =>
    Results.Content(
        """
        <!doctype html>
        <html lang="en">
          <head>
            <meta charset="utf-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1" />
            <title>Amicable ASP.NET Core</title>
            <style>
              body { font-family: ui-sans-serif, system-ui, sans-serif; margin: 2rem; color: #0f172a; }
              .box { max-width: 42rem; border: 1px solid #cbd5e1; border-radius: 12px; padding: 1rem 1.25rem; }
            </style>
          </head>
          <body>
            <div class="box">
              <h1>ASP.NET Core sandbox is running</h1>
              <p>Edit <code>Program.cs</code> and refresh the preview.</p>
            </div>
          </body>
        </html>
        """,
        "text/html"));

app.Run();
