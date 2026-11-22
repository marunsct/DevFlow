"""An HTTP service in C#, on ASP.NET Core minimal APIs."""

from __future__ import annotations

from app.stacks.packs._service import service_pack
from app.stacks.packs import _sandbox as sandbox

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
src/App package <name>`. The service reads its settings through `builder.Configuration`
(`builder.Configuration["DATA_DIR"]`), which holds the environment's variables too; so a test
that needs data of its own gives its factory a folder of its own with
`factory.WithWebHostBuilder(b => b.UseSetting("DATA_DIR", folder)).CreateClient()`, the folder a
new one under `Path.GetTempPath()`. No test needs a factory class of its own."""

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

#: The project file's SDK, held at every round (`StackPack.required_signatures`). Measured on two C# runs: `App.csproj`
#: was rewritten to `Sdk="Microsoft.NET.Sdk"`, which drops ASP.NET Core and its implicit usings, and the build then
#: failed in every file that names `HttpContext`, `IResult` or `Results`, never in the project file itself.
APP_SDK = {"src/App/App.csproj": ((r'<Project\s+Sdk="Microsoft\.NET\.Sdk\.Web"', '<Project Sdk="Microsoft.NET.Sdk.Web">'),)}

#: The pack's golden example (`StackPack.golden_example`), on .NET 8 minimal APIs: the store registered once as a
#: service and named as an endpoint's parameter, `DATA_DIR` read from `IConfiguration` when the store is first made (so
#: a test's `UseSetting` reaches it), `Results.BadRequest`, `Results.Created` and `Results.NotFound`, and a test
#: through `WebApplicationFactory<Program>` with a data folder of its own.
GOLDEN_PROGRAM = r"""using System.Text.Json;

var builder = WebApplication.CreateBuilder(args);
// Shared state: one store for the process, made the first time an endpoint asks for it.
builder.Services.AddSingleton<ItemStore>(services =>
    new ItemStore(services.GetRequiredService<IConfiguration>()["DATA_DIR"] ?? "data"));
var app = builder.Build();

app.MapGet("/health", () => Results.Ok(new { status = "ok" }));

app.MapPost("/items", (NewItem? body, ItemStore store) =>
{
    if (body is null || string.IsNullOrWhiteSpace(body.Name))
    {
        return Results.BadRequest(new { error = "name is required" });
    }
    var item = store.Add(body.Name.Trim());
    return Results.Created($"/items/{item.Id}", item);
});

app.MapGet("/items/{id:int}", (int id, ItemStore store) =>
    store.Find(id) is { } item ? Results.Ok(item) : Results.NotFound(new { error = "item not found" }));

var host = Environment.GetEnvironmentVariable("HOST") ?? "127.0.0.1";
var port = Environment.GetEnvironmentVariable("PORT") ?? "5000";
app.Urls.Add($"http://{host}:{port}");
app.Run();

public record NewItem(string? Name);

public record Item(int Id, string Name);

/// <summary>The items, kept in one JSON file under DATA_DIR; one lock covers each read-change-write.</summary>
public class ItemStore
{
    private readonly string _file;
    private readonly object _lock = new();

    public ItemStore(string dataDir) => _file = Path.GetFullPath(Path.Combine(dataDir, "items.json"));

    public Item Add(string name)
    {
        lock (_lock)
        {
            var items = Load();
            var item = new Item(items.Count == 0 ? 1 : items.Max(i => i.Id) + 1, name);
            items.Add(item);
            Directory.CreateDirectory(Path.GetDirectoryName(_file)!);
            File.WriteAllText(_file, JsonSerializer.Serialize(items));
            return item;
        }
    }

    public Item? Find(int id)
    {
        lock (_lock)
        {
            return Load().FirstOrDefault(i => i.Id == id);
        }
    }

    private List<Item> Load() =>
        File.Exists(_file) ? JsonSerializer.Deserialize<List<Item>>(File.ReadAllText(_file)) ?? new List<Item>() : new List<Item>();
}

// The entry point, visible to the unit tests' WebApplicationFactory.
public partial class Program { }
"""

GOLDEN_TEST = r"""using System.Net;
using System.Net.Http.Json;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Xunit;

public class ItemsTests : IClassFixture<WebApplicationFactory<Program>>
{
    private readonly WebApplicationFactory<Program> _factory;

    public ItemsTests(WebApplicationFactory<Program> factory) => _factory = factory;

    // Each test's service keeps its data in a folder of its own.
    private HttpClient ClientWithItsOwnData()
    {
        var folder = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N"));
        return _factory.WithWebHostBuilder(b => b.UseSetting("DATA_DIR", folder)).CreateClient();
    }

    [Fact]
    public void AnItemIsStoredAndReadBack()
    {
        var client = ClientWithItsOwnData();
        var created = client.PostAsJsonAsync("/items", new { name = "first" }).GetAwaiter().GetResult();
        Assert.Equal(HttpStatusCode.Created, created.StatusCode);
        var item = created.Content.ReadFromJsonAsync<Item>().GetAwaiter().GetResult();
        var found = client.GetFromJsonAsync<Item>($"/items/{item!.Id}").GetAwaiter().GetResult();
        Assert.Equal("first", found!.Name);
    }

    [Fact]
    public void AMissingNameIsRefusedAndAnUnknownIdIsNotFound()
    {
        var client = ClientWithItsOwnData();
        var refused = client.PostAsJsonAsync("/items", new { }).GetAwaiter().GetResult();
        Assert.Equal(HttpStatusCode.BadRequest, refused.StatusCode);
        var missing = client.GetAsync("/items/99").GetAwaiter().GetResult();
        Assert.Equal(HttpStatusCode.NotFound, missing.StatusCode);
    }
}
"""

#: Errors a C# service is known to raise, by a phrase of the compiler's message, and their cause
#: (`app.stacks.known_errors`). Measured on two runs (C# 13 and 14): the entry file's top-level statements failed to
#: compile on a rule of local functions, and the fixers rewrote the file for rounds without naming it.
CSHARP_KNOWN_ERRORS = {
    "The modifier 'public' is not valid for this item": (
        "In `Program.cs`'s top-level statements a local function or variable takes no access modifier (`public`, "
        "`private`, `internal`): write it plain, or move it into a `static class` declared after the statements."
    ),
    "A static local function cannot contain a reference to": (
        "A `static` local function cannot read the enclosing code's local variables: pass the value in as a parameter, "
        "or drop `static` from the function."
    ),
}

PACK = service_pack(
    golden_example={"src/App/Program.cs": GOLDEN_PROGRAM, "tests/UnitTests/ItemsTests.cs": GOLDEN_TEST},
    known_errors=CSHARP_KNOWN_ERRORS,
    sandbox_image=sandbox.DOTNET,
    required_signatures=APP_SDK,
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
    entrypoint="src/App/Program.cs",
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
    kept_lines=(("tests/UnitTests/UnitTests.csproj", r'Include="JunitXml\.TestLogger"',
                 '    <PackageReference Include="JunitXml.TestLogger" Version="6.1.0" />', r"^\s*</ItemGroup>"),),
)
