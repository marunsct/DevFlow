package app.notes_api;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.jdbc.core.JdbcTemplate;

import java.nio.file.Files;
import java.nio.file.Paths;

/**
 * Application entry point. Creates the DATA_DIR directory at startup and
 * ensures the 'notes' table exists when the application context is ready.
 *
 * <p>Flow:
 * <ol>
 *   <li>main() creates DATA_DIR (if missing) and starts Spring Boot.</li>
 *   <li>Spring Boot auto-configures a JdbcTemplate backed by SQLite
 *       (url set in application.properties).</li>
 *   <li>When the context is ready, initTable() runs CREATE TABLE IF NOT EXISTS
 *       so the notes table is created on first start.</li>
 * </ol>
 *
 * <p>Security: the @EventListener method uses a constructor-injected JdbcTemplate
 * field rather than a parameter, because Spring passes the event object to
 * event listeners — not the parameter type. Declaring JdbcTemplate as a parameter
 * would cause an "argument type mismatch" (ApplicationReadyEvent cannot be
 * converted to JdbcTemplate).
 */
@SpringBootApplication
public class Application {

    private final JdbcTemplate jdbcTemplate;

    /**
     * Constructor injection for JdbcTemplate.
     * Spring provides the jdbcTemplate bean configured in application.properties.
     */
    public Application(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public static void main(String[] args) {
        String dataDir = System.getenv("DATA_DIR") != null ? System.getenv("DATA_DIR") : "data";
        try {
            Files.createDirectories(Paths.get(dataDir));
        } catch (Exception e) {
            // If we can't create the directory, let the application fail or handle it gracefully.
            // The spec says "Creates DATA_DIR directory if it does not exist".
            // We proceed anyway; Spring Boot will likely fail on DB connection if dir is missing/invalid.
        }
        SpringApplication.run(Application.class, args);
    }

    /**
     * Called by Spring when the application context is ready.
     * Creates the notes table if it does not already exist.
     *
     * <p>No parameters: Spring passes the ApplicationReadyEvent to the method,
     * but we do not need it. The JdbcTemplate is available as an instance field
     * injected via constructor.
     */
    @EventListener(ApplicationReadyEvent.class)
    public void initTable() {
        jdbcTemplate.execute("CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, body TEXT NOT NULL)");
    }
}
