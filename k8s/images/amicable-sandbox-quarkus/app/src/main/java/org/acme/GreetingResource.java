package org.acme;

import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;

@Path("/")
public class GreetingResource {

    @GET
    @Produces(MediaType.TEXT_HTML)
    public String hello() {
        return """
            <!doctype html>
            <html lang="en">
              <head>
                <meta charset="utf-8" />
                <meta name="viewport" content="width=device-width, initial-scale=1" />
                <title>Amicable Quarkus</title>
                <style>
                  body { font-family: ui-sans-serif, system-ui, sans-serif; margin: 2rem; color: #0f172a; }
                  .box { max-width: 42rem; border: 1px solid #cbd5e1; border-radius: 12px; padding: 1rem 1.25rem; }
                </style>
              </head>
              <body>
                <div class="box">
                  <h1>Quarkus sandbox is running</h1>
                  <p>Edit <code>GreetingResource.java</code> and refresh the preview.</p>
                </div>
              </body>
            </html>
            """;
    }
}
