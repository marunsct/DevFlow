"""An HTTP service in C#, on ASP.NET Core minimal APIs."""

from __future__ import annotations

from app.stacks.packs._service import service_pack

DOTNET = "8.0"

APP_CSPROJ = """<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup>
    <TargetFramework>net%s</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
    <RootNamespace>App</RootNamespace>
    <AssemblyName>App</AssemblyName>
  </PropertyGroup>
</Project>
""" % DOTNET

PROGRAM = """var builder = WebApplication.CreateBuilder(args);
var app = builder.Build();

app.MapGet("/health", () => Results.Ok(new { status = "ok" }));

var host = Environment.GetEnvironmentVariable("HOST") ?? "127.0.0.1";
var port = Environment.GetEnvironmentVariable("PORT") ?? "5000";
app.Urls.Add($"http://{host}:{port}");
app.Run();

// The entry point, visible to the unit tests' WebApplicationFactory.
public partial class Program { }
"""

TESTS_CSPROJ = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net%(dotnet)s</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
    <IsPackable>false</IsPackable>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.12.0" />
    <PackageReference Include="xunit" Version="2.9.3" />
    <PackageReference Include="xunit.runner.visualstudio" Version="3.0.2" />
    <PackageReference Include="Microsoft.AspNetCore.Mvc.Testing" Version="8.0.11" />
    <PackageReference Include="JunitXml.TestLogger" Version="6.1.0" />
  </ItemGroup>
  <ItemGroup>
    <ProjectReference Include="../../src/App/App.csproj" />
  </ItemGroup>
</Project>
""" % {"dotnet": DOTNET}

SMOKE_UNIT = """using System.Net.Http.Json;
using Microsoft.AspNetCore.Mvc.Testing;
using Xunit;

public class ScaffoldSmokeTests : IClassFixture<WebApplicationFactory<Program>>
{
    private readonly HttpClient _client;

    public ScaffoldSmokeTests(WebApplicationFactory<Program> factory) => _client = factory.CreateClient();

    [Fact]
    public async Task TheServiceReportsItsHealth()
    {
        var health = await _client.GetFromJsonAsync<Dictionary<string, string>>("/health");
        Assert.Equal("ok", health!["status"]);
    }
}
"""

GUIDE = """The service is C# on ASP.NET Core minimal APIs: `src/App/Program.cs` builds and starts
it (map endpoints with `app.MapGet`, `app.MapPost` ...; keep `public partial class
Program { }` at its end). Unit tests go in `tests/UnitTests/`, named `<Name>Tests.cs`,
using xUnit (`[Fact]`) and `WebApplicationFactory<Program>` to call the endpoints in
memory. Run them with `dotnet test tests/UnitTests`. Add a package with `dotnet add
src/App package <name>`."""

DOCKERFILE = """# {{title}}: build with `docker build -t {{project}} .`, run with
# `docker run -p 8080:8080 -v {{project}}-data:/data {{project}}`.
FROM mcr.microsoft.com/dotnet/sdk:%(dotnet)s AS build
WORKDIR /src
COPY src/App/App.csproj src/App/
RUN dotnet restore src/App/App.csproj
COPY . .
RUN dotnet publish src/App/App.csproj -c Release -o /out

FROM mcr.microsoft.com/dotnet/aspnet:%(dotnet)s
ENV HOST=0.0.0.0 PORT=8080 DATA_DIR=/data
WORKDIR /app
COPY --from=build /out ./
USER app
EXPOSE 8080
ENTRYPOINT ["dotnet", "App.dll"]
""" % {"dotnet": DOTNET}

PACK = service_pack(
    name="csharp-aspnet-api",
    title="HTTP service in C# on ASP.NET Core",
    language="csharp",
    frameworks=("asp.net", "aspnet", "asp.net core", "aspnetcore", "minimal api", ".net", "dotnet"),
    files={
        "src/App/App.csproj": APP_CSPROJ,
        "src/App/Program.cs": PROGRAM,
        "tests/UnitTests/UnitTests.csproj": TESTS_CSPROJ,
    },
    install=(("dotnet", "restore", "tests/UnitTests"), ("dotnet", "build", "tests/UnitTests", "--no-restore")),
    unit_test=(
        "dotnet", "test", "tests/UnitTests", "--logger",
        "junit;LogFilePath=../../test-results/unit.xml;MethodFormat=Class;FailureBodyFormat=Verbose",
    ),
    unit_report="test-results/unit.xml",
    unit_dir="tests",
    unit_pattern="*Tests.cs",
    start="exec dotnet run --project src/App --no-launch-profile",
    server_timeout_ms=240_000,
    smoke_unit=("tests/UnitTests/ScaffoldSmokeTests.cs", SMOKE_UNIT),
    guide=GUIDE,
    stack={
        "language": "C#",
        "framework": "ASP.NET Core",
        "frontend_framework": "",
        "testing_framework": "xUnit with WebApplicationFactory for unit tests, Playwright (request fixture) for acceptance tests",
    },
    ci_setup=(
        "      - uses: actions/setup-dotnet@v4\n"
        "        with:\n"
        f'          dotnet-version: "{DOTNET}.x"',
    ),
    release_files={"Dockerfile": DOCKERFILE, ".dockerignore": "node_modules/\ntest-results/\n**/bin/\n**/obj/\nacceptance/\ndata/\n"},
    gitignore="bin/\nobj/\n",
)
