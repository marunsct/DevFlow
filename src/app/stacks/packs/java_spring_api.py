"""An HTTP service in Java, on Spring Boot, built with Maven."""

from __future__ import annotations

from app.stacks import ReleaseFamily, ReleaseLine
from app.stacks.packs._service import service_pack
from app.stacks.packs import _sandbox as sandbox

JAVA_VERSION = "21"
SPRING_BOOT = "3.4.5"

POM_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>%(boot)s</version>
    <relativePath/>
  </parent>
  <groupId>app</groupId>
  <artifactId>{{package}}</artifactId>
  <version>0.1.0</version>
  <name>{{title}}</name>
  <properties>
    <java.version>%(java)s</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>%(web)s</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>%(test)s</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <finalName>app</finalName>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
"""
POM = POM_TEMPLATE % {"boot": SPRING_BOOT, "java": JAVA_VERSION, "web": "spring-boot-starter-web",
                      "test": "spring-boot-starter-test"}
#: On the Spring Boot 4 line (LF.1311): `spring-boot-starter-web` is deprecated for `spring-boot-starter-webmvc`, and
#: each technology has its own test starter - `@WebMvcTest` comes with `spring-boot-starter-webmvc-test`, which brings
#: `spring-boot-starter-test` (the 4.0 migration guide; read from the 4.2.0 POMs and jars on Maven Central). The
#: parent's version is the family's place, so the release chosen is written into it.
POM_4 = POM_TEMPLATE % {"boot": "4.0.0", "java": JAVA_VERSION, "web": "spring-boot-starter-webmvc",
                        "test": "spring-boot-starter-webmvc-test"}

APPLICATION = """package app.{{package}};

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
"""

HEALTH = """package app.{{package}};

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HealthController {
    @GetMapping("/health")
    public Map<String, String> health() {
        return Map.of("status", "ok");
    }
}
"""

PROPERTIES = """server.port=${PORT:8080}
server.address=${HOST:127.0.0.1}
spring.main.banner-mode=off
"""

SMOKE_UNIT_TEMPLATE = """package app.{{package}};

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import %(web_mvc_test)s;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(HealthController.class)
class ScaffoldSmokeTest {
    @Autowired
    private MockMvc mvc;

    @Test
    void theServiceReportsItsHealth() throws Exception {
        mvc.perform(get("/health")).andExpect(status().isOk()).andExpect(jsonPath("$.status").value("ok"));
    }
}
"""
SMOKE_UNIT = SMOKE_UNIT_TEMPLATE % {"web_mvc_test": "org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest"}
#: `@WebMvcTest` moved in Spring Boot 4 (read from the 4.2.0 `spring-boot-webmvc-test` jar).
SMOKE_UNIT_4 = SMOKE_UNIT_TEMPLATE % {"web_mvc_test": "org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest"}
SMOKE_UNIT_PATH = "src/test/java/app/{{package}}/ScaffoldSmokeTest.java"

GUIDE = """The service is Java on Spring Boot, built with Maven: code in
`src/main/java/app/{{package}}/` (`Application.java` starts it; add `@RestController`
classes beside `HealthController.java`), configuration in
`src/main/resources/application.properties`. Unit tests go in
`src/test/java/app/{{package}}/`, named `<Name>Test.java`, using JUnit 5 and Spring's
test support (`@WebMvcTest` with `MockMvc` for a controller, plain JUnit for the rest).
A `@WebMvcTest` replaces each service with a `@MockitoBean` stand-in, so it checks what the
controller does itself; a rule the service enforces (a field it refuses) is tested in the
service's own JUnit test, or in a `@SpringBootTest` with the real service.
Run them with `mvn -q -B test`. Add a dependency to `pom.xml`."""

DOCKERFILE = """# {{title}}: build with `docker build -t {{project}} .`, run with
# `docker run -p 8080:8080 -v {{project}}-data:/data {{project}}`.
FROM maven:3.9-eclipse-temurin-%(java)s AS build
WORKDIR /src
COPY pom.xml ./
RUN mvn -q -B dependency:go-offline
COPY . .
RUN mvn -q -B -Dmaven.test.skip=true package

FROM eclipse-temurin:%(java)s-jre
ENV HOST=0.0.0.0 PORT=8080 DATA_DIR=/data
WORKDIR /app
COPY --from=build /src/target/app.jar ./app.jar
RUN useradd --create-home --uid 10001 app && mkdir -p /data && chown app:app /data
USER app
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
""" % {"java": JAVA_VERSION}

#: Errors a Spring Boot service is known to raise, by a phrase of the compiler's message, and their cause
#: (`app.stacks.known_errors`). Measured on one run: a controller test imported `org.springframework.boot.test.mock.bean.
#: MockBean`, a package that does not exist, and the first fix left it so.
SPRING_KNOWN_ERRORS = {
    "package jakarta.validation does not exist": (
        "`jakarta.validation` (`@Valid`, `@NotBlank`) comes with the `spring-boot-starter-validation` dependency, "
        "which `pom.xml` must declare beside `spring-boot-starter-web`; the version is the parent's."
    ),
    # Measured on one run: the stack was chosen as "SQLite via H2's SQLite compatibility mode" - H2 has no such mode -
    # and the SQLite advice (WAL, a busy timeout) went into H2's URL; the service exited at start for two attempts.
    "Unsupported connection setting": (
        "H2 refused a setting written into its JDBC URL. H2 has no SQLite mode and takes none of SQLite's settings "
        "(`BUSY_TIMEOUT`, `journal_mode`): keep H2's URL to H2's own settings, or store in SQLite itself through "
        "`org.xerial:sqlite-jdbc` with `org.hibernate.orm:hibernate-community-dialects` "
        "(`spring.jpa.database-platform=org.hibernate.community.dialect.SQLiteDialect`) - or in a JSON file, as the "
        "golden example does."
    ),
    # Measured on two Java runs (about 42 repeats of the line in one): the service exited at start with this message and
    # three rounds of fixes rewrote `pom.xml` and the controller, which are not where it comes from.
    "Unable to determine Dialect without JDBC metadata": (
        "Hibernate could not get a database connection to ask its dialect, or has no dialect for SQLite. First check "
        "that the folder the JDBC URL names exists before the first connection (create `DATA_DIR` at start; "
        "`jdbc:sqlite:${DATA_DIR}/...` fails when it does not) and that the property has a default. Then, with "
        "`org.xerial:sqlite-jdbc`, add `org.hibernate.orm:hibernate-community-dialects` and set "
        "`spring.jpa.database-platform=org.hibernate.community.dialect.SQLiteDialect`. Or skip JPA and keep a plain "
        "JSON file, as the golden example does."
    ),
    # Measured on two Java runs (Java 7 and Java 9): the service answered 500 to every request with `path to
    # '<folder>/notes.db': '<folder>' does not exist`; SQLite's driver creates the file and never its folder, and the
    # acceptance suite hands the service a fresh data folder that is not there yet.
    "path to '": (
        "SQLite's JDBC driver creates the database file but not the folder it sits in, and the suite gives the "
        "service a fresh data folder (`DATA_DIR`) that does not exist yet: create it before the first connection "
        "(`Files.createDirectories(Path.of(dataDir))` in the bean that builds the `DataSource`, or at start-up before "
        "`SpringApplication.run`) and create the table there too."
    ),
    "package org.springframework.boot.test.mock.bean does not exist": (
        "`@MockBean` is `org.springframework.boot.test.mock.mockito.MockBean` (deprecated since Spring Boot 3.4); "
        "its replacement is `@MockitoBean` from `org.springframework.test.context.bean.override.mockito`, which "
        "exists only from Spring Boot 3.4 on (the parent's version in `pom.xml`)."
    ),
    # LF.1613, measured on one Java run: the specification set the parent to Spring Boot 3.2.5, a controller test used
    # `@MockitoBean` (Spring Framework 6.2, which Boot 3.4 brings; read from the 3.2.5 and 3.4.5 jars), and each fix
    # swapped it for a `MockBean` package that does not exist either.
    "package org.springframework.test.context.bean.override.mockito does not exist": (
        "`@MockitoBean` comes with Spring Framework 6.2, which Spring Boot 3.4 and later bring. Under an earlier "
        "Spring Boot parent in `pom.xml`, use `@MockBean` from `org.springframework.boot.test.mock.mockito` (in "
        "`spring-boot-starter-test`); the package `org.springframework.boot.test.mock.bean` does not exist."
    ),
    # LF.1613, measured on one Java run: the specification asked for a configuration class building a Hibernate
    # `SessionFactory` bean for SQLite's settings; the service exited at start with this message, and no fix was given
    # that class. Read from the Spring Boot 3.2.5 and 3.4.5 jars: `JpaBaseConfiguration.entityManagerFactory` is
    # `@ConditionalOnMissingBean({LocalContainerEntityManagerFactoryBean, EntityManagerFactory})`, and Hibernate 6's
    # `SessionFactory` extends `jakarta.persistence.EntityManagerFactory`; sqlite-jdbc reads `journal_mode` and
    # `busy_timeout` from the JDBC URL's query.
    "a bean named 'entityManagerFactory' that could not be found": (
        "Spring Boot builds the JPA `EntityManagerFactory` - the bean `entityManagerFactory` that Spring Data "
        "repositories are wired to - only when the application declares no `EntityManagerFactory` of its own. "
        "Hibernate's `SessionFactory` is an `EntityManagerFactory`, so a hand-written `@Bean` returning a "
        "`SessionFactory` (or a `LocalSessionFactoryBean`, or an `EntityManagerFactory` by another name) makes Boot "
        "build none, and the repositories find no `entityManagerFactory`. Remove that `@Bean` - the `@Configuration` "
        "class that declares it, when that is all it holds - and let Boot build it from `spring.datasource.*` and "
        "`spring.jpa.*` in `application.properties`. SQLite's settings go in the JDBC URL's query "
        "(`jdbc:sqlite:${DATA_DIR}/app.db?journal_mode=WAL&busy_timeout=5000`), not in Hibernate properties. "
        "Without `spring-boot-starter-data-jpa` in `pom.xml` there is no such bean either."
    ),
}

#: The pack's golden example (`StackPack.golden_example`), in Spring Boot 3.4: a store bean given to the controller
#: through its constructor, `DATA_DIR` read through `@Value` (the environment is a property source), `ResponseEntity`
#: for 201, 400 and 404, Jackson (in the web starter) for the file, and a plain JUnit test over a standalone `MockMvc`.
GOLDEN_STORE = r"""package app.{{package}};

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/** The items, kept in one JSON file under DATA_DIR; one lock covers each read-change-write. */
@Component
public class ItemStore {
    public record Item(long id, String name) {}

    private final Path file;
    private final ObjectMapper json = new ObjectMapper();

    public ItemStore(@Value("${DATA_DIR:data}") String dataDir) {
        this.file = Path.of(dataDir, "items.json");
    }

    public synchronized Item add(String name) {
        List<Item> items = load();
        long next = items.stream().mapToLong(Item::id).max().orElse(0) + 1;
        Item item = new Item(next, name);
        items.add(item);
        save(items);
        return item;
    }

    public synchronized Optional<Item> find(long id) {
        return load().stream().filter(item -> item.id() == id).findFirst();
    }

    private List<Item> load() {
        try {
            if (!Files.exists(file)) {
                return new ArrayList<>();
            }
            return new ArrayList<>(json.readValue(file.toFile(), new TypeReference<List<Item>>() {}));
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    private void save(List<Item> items) {
        try {
            Files.createDirectories(file.toAbsolutePath().getParent());
            json.writeValue(file.toFile(), items);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }
}
"""

#: The golden example's store on the Spring Boot 4 line (LF.1311): Jackson 3 under `tools.jackson.*`, whose exceptions are
#: unchecked, so the file is read and written by `Files` (what throws `IOException` here) and the JSON is a string.
GOLDEN_STORE_4 = r"""package app.{{package}};

import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.json.JsonMapper;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/** The items, kept in one JSON file under DATA_DIR; one lock covers each read-change-write. */
@Component
public class ItemStore {
    public record Item(long id, String name) {}

    private final Path file;
    private final JsonMapper json = JsonMapper.builder().build();

    public ItemStore(@Value("${DATA_DIR:data}") String dataDir) {
        this.file = Path.of(dataDir, "items.json");
    }

    public synchronized Item add(String name) {
        List<Item> items = load();
        long next = items.stream().mapToLong(Item::id).max().orElse(0) + 1;
        Item item = new Item(next, name);
        items.add(item);
        save(items);
        return item;
    }

    public synchronized Optional<Item> find(long id) {
        return load().stream().filter(item -> item.id() == id).findFirst();
    }

    private List<Item> load() {
        try {
            if (!Files.exists(file)) {
                return new ArrayList<>();
            }
            return new ArrayList<>(json.readValue(Files.readString(file), new TypeReference<List<Item>>() {}));
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    private void save(List<Item> items) {
        try {
            Files.createDirectories(file.toAbsolutePath().getParent());
            Files.writeString(file, json.writeValueAsString(items));
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }
}
"""

GOLDEN_CONTROLLER = r"""package app.{{package}};

import java.util.Map;
import java.util.Optional;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/items")
public class ItemController {
    public record NewItem(String name) {}

    private final ItemStore store;

    public ItemController(ItemStore store) {
        this.store = store;
    }

    @PostMapping
    public ResponseEntity<?> create(@RequestBody(required = false) NewItem body) {
        if (body == null || body.name() == null || body.name().isBlank()) {
            return ResponseEntity.badRequest().body(Map.of("error", "name is required"));
        }
        return ResponseEntity.status(HttpStatus.CREATED).body(store.add(body.name().trim()));
    }

    @GetMapping("/{id}")
    public ResponseEntity<?> find(@PathVariable("id") long id) {
        Optional<ItemStore.Item> found = store.find(id);
        if (found.isEmpty()) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of("error", "item not found"));
        }
        return ResponseEntity.ok(found.get());
    }
}
"""

GOLDEN_TEST = r"""package app.{{package}};

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.nio.file.Path;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

class ItemControllerTest {
    @TempDir
    Path dataDir;

    private MockMvc mvc;

    @BeforeEach
    void setUp() {
        mvc = MockMvcBuilders.standaloneSetup(new ItemController(new ItemStore(dataDir.toString()))).build();
    }

    @Test
    void anItemIsStoredAndReadBack() throws Exception {
        mvc.perform(post("/items").contentType(MediaType.APPLICATION_JSON).content("{\"name\":\"first\"}"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.id").value(1));
        mvc.perform(get("/items/1"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("first"));
    }

    @Test
    void aMissingNameIsRefusedAndAnUnknownIdIsNotFound() throws Exception {
        mvc.perform(post("/items").contentType(MediaType.APPLICATION_JSON).content("{}"))
            .andExpect(status().isBadRequest());
        mvc.perform(get("/items/99")).andExpect(status().isNotFound());
    }
}
"""

#: Errors a Spring Boot 4 service is known to raise (LF.1311), from the 4.0 migration guide and the 4.2.0 jars: code
#: written from memory of the 3.x line meets these first.
SPRING_4_KNOWN_ERRORS = {
    "package jakarta.validation does not exist": (
        "`jakarta.validation` (`@Valid`, `@NotBlank`) comes with the `spring-boot-starter-validation` dependency, "
        "which `pom.xml` must declare beside `spring-boot-starter-webmvc`; the version is the parent's."
    ),
    "package com.fasterxml.jackson.databind does not exist": (
        "Spring Boot 4 brings Jackson 3, whose packages are `tools.jackson.*`: `tools.jackson.databind.json.JsonMapper` "
        "(or `tools.jackson.databind.ObjectMapper`) and `tools.jackson.core.type.TypeReference`; only the annotations "
        "stay in `com.fasterxml.jackson.annotation`. Jackson 3's exceptions are unchecked, so a `catch (IOException e)` "
        "must wrap something that still throws it (`Files.readString`, `Files.writeString`)."
    ),
    "package com.fasterxml.jackson.core": (
        "Spring Boot 4 brings Jackson 3: `TypeReference` is `tools.jackson.core.type.TypeReference`, and the rest of "
        "Jackson is under `tools.jackson.*`; only the annotations stay in `com.fasterxml.jackson.annotation`."
    ),
    "package org.springframework.boot.test.autoconfigure.web.servlet does not exist": (
        "In Spring Boot 4, `@WebMvcTest` and `@AutoConfigureMockMvc` are in "
        "`org.springframework.boot.webmvc.test.autoconfigure`, from the `spring-boot-starter-webmvc-test` dependency "
        "(test scope)."
    ),
    "package org.springframework.boot.test.web.client does not exist": (
        "In Spring Boot 4, `TestRestTemplate` is `org.springframework.boot.resttestclient.TestRestTemplate`, and a "
        "`@SpringBootTest` gets one only with `@AutoConfigureTestRestTemplate` "
        "(`org.springframework.boot.resttestclient.autoconfigure`)."
    ),
    "package org.springframework.boot.test.mock.mockito does not exist": (
        "Spring Boot 4 removed `@MockBean` and `@SpyBean`: use `@MockitoBean` and `@MockitoSpyBean` from "
        "`org.springframework.test.context.bean.override.mockito`."
    ),
}

#: Spring Boot, the release this pack pins (LF.1311): a brief asking for another line has the parent's version - which
#: sets the starters', plugins' and BOM's - written at the newest release of that line the toolchain runs. Maven
#: Central's `spring-boot-starter-parent` leads the line; the 4 line gets its own starters, smoke test, golden store and
#: known errors.
SPRING_BOOT_RELEASES = ReleaseFamily(
    title="Spring Boot",
    names=("spring boot", "springboot", "spring-boot-starter-parent"),
    ecosystem="maven",
    package="org.springframework.boot:spring-boot-starter-parent",
    places=(("org.springframework.boot:spring-boot-starter-parent", "pom.xml",
             r"<artifactId>spring-boot-starter-parent</artifactId>\s*<version>(?P<version>[^<\s]+)</version>"),),
    lines={"4": ReleaseLine(
        files={"pom.xml": POM_4},
        smoke_files={SMOKE_UNIT_PATH: SMOKE_UNIT_4},
        golden_example={"src/main/java/app/{{package}}/ItemStore.java": GOLDEN_STORE_4},
        known_errors=SPRING_4_KNOWN_ERRORS,
    )},
)

#: The build's jar name, held at every round (`StackPack.required_signatures`): the pack's `start.sh` and Dockerfile run
#: `target/app.jar`. Measured on one Java run: a work order rewrote `pom.xml` without `<finalName>app</finalName>`, the
#: build made `notes-api-1.0.0.jar`, and every start said "Unable to access jarfile target/app.jar" for a whole attempt.
JAR_NAME = {"pom.xml": ((r"<finalName>\s*app\s*</finalName>", "<finalName>app</finalName>"),)}

PACK = service_pack(
    release_families=(SPRING_BOOT_RELEASES,),
    golden_example={
        "src/main/java/app/{{package}}/ItemStore.java": GOLDEN_STORE,
        "src/main/java/app/{{package}}/ItemController.java": GOLDEN_CONTROLLER,
        "src/test/java/app/{{package}}/ItemControllerTest.java": GOLDEN_TEST,
    },
    known_errors=SPRING_KNOWN_ERRORS,
    required_signatures=JAR_NAME,
    sandbox_image=sandbox.JAVA,
    name="java-spring-api",
    title="HTTP service in Java on Spring Boot",
    language="java",
    frameworks=("spring", "spring boot", "springboot", "spring-boot"),
    files={
        "pom.xml": POM,
        "src/main/java/app/{{package}}/Application.java": APPLICATION,
        "src/main/java/app/{{package}}/HealthController.java": HEALTH,
        "src/main/resources/application.properties": PROPERTIES,
    },
    # `-Dmaven.test.skip`, not `-DskipTests`: the product is built without compiling its tests. Measured on one run, a
    # unit test naming a class that did not exist stopped `start.sh` - every acceptance and hidden test failed on a
    # product whose own code compiled. The unit command still compiles and runs the tests.
    install=(("mvn", "-q", "-B", "-Dmaven.test.skip=true", "package"),),
    unit_test=("mvn", "-q", "-B", "test"),
    # Surefire fetches its JUnit provider the first time a test runs, not at the install; one test run with the
    # network, its failures ignored, puts it in the run's Maven cache before the offline test commands need it.
    warm_up=(("mvn", "-q", "-B", "-Dmaven.test.failure.ignore=true", "test"),),
    unit_report="target/surefire-reports",
    unit_dir="src/test",
    unit_mirrors=("src/main/java", "src/test/java"),
    # Maven resolves a plugin's dependencies when a build first reaches it, so a changed version is fetched by the
    # build or test that needs it, not by an install a compile error stopped early.
    fetches_while_building=True,
    unit_pattern="*Test.java",
    start="mvn -q -B -Dmaven.test.skip=true package && exec java -jar target/app.jar",
    server_timeout_ms=300_000,
    smoke_unit=(SMOKE_UNIT_PATH, SMOKE_UNIT),
    guide=GUIDE,
    stack={
        "language": "Java",
        "framework": "Spring Boot",
        "frontend_framework": "",
        "testing_framework": "JUnit 5 with Spring Boot Test for unit tests, Playwright (request fixture) for acceptance tests",
    },
    ci_setup=(
        "      - uses: actions/setup-java@v4\n"
        "        with:\n"
        "          distribution: temurin\n"
        f'          java-version: "{JAVA_VERSION}"\n'
        "          cache: maven",
    ),
    release_files={"Dockerfile": DOCKERFILE, ".dockerignore": "node_modules/\ntest-results/\ntarget/\nacceptance/\ndata/\n"},
    gitignore="target/\n",
)
