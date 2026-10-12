"""An HTTP service in Java, on Spring Boot, built with Maven."""

from __future__ import annotations

from app.stacks.packs._service import service_pack

JAVA_VERSION = "21"
SPRING_BOOT = "3.4.5"

POM = """<?xml version="1.0" encoding="UTF-8"?>
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
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
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
""" % {"boot": SPRING_BOOT, "java": JAVA_VERSION}

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

SMOKE_UNIT = """package app.{{package}};

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
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

GUIDE = """The service is Java on Spring Boot, built with Maven: code in
`src/main/java/app/{{package}}/` (`Application.java` starts it; add `@RestController`
classes beside `HealthController.java`), configuration in
`src/main/resources/application.properties`. Unit tests go in
`src/test/java/app/{{package}}/`, named `<Name>Test.java`, using JUnit 5 and Spring's
test support (`@WebMvcTest` with `MockMvc` for a controller, plain JUnit for the rest).
Run them with `mvn -q -B test`. Add a dependency to `pom.xml`."""

DOCKERFILE = """# {{title}}: build with `docker build -t {{project}} .`, run with
# `docker run -p 8080:8080 -v {{project}}-data:/data {{project}}`.
FROM maven:3.9-eclipse-temurin-%(java)s AS build
WORKDIR /src
COPY pom.xml ./
RUN mvn -q -B dependency:go-offline
COPY . .
RUN mvn -q -B -DskipTests package

FROM eclipse-temurin:%(java)s-jre
ENV HOST=0.0.0.0 PORT=8080 DATA_DIR=/data
WORKDIR /app
COPY --from=build /src/target/app.jar ./app.jar
RUN useradd --create-home --uid 10001 app && mkdir -p /data && chown app:app /data
USER app
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
""" % {"java": JAVA_VERSION}

PACK = service_pack(
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
    install=(("mvn", "-q", "-B", "-DskipTests", "package"),),
    unit_test=("mvn", "-q", "-B", "test"),
    unit_report="target/surefire-reports",
    unit_dir="src/test",
    unit_pattern="*Test.java",
    start="mvn -q -B -DskipTests package && exec java -jar target/app.jar",
    server_timeout_ms=300_000,
    smoke_unit=("src/test/java/app/{{package}}/ScaffoldSmokeTest.java", SMOKE_UNIT),
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
