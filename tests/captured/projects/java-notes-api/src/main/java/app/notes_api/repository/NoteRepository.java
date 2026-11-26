package app.notes_api.repository;

import app.notes_api.model.Note;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Repository;

import java.sql.PreparedStatement;
import java.sql.Statement;
import java.util.List;

@Repository
public class NoteRepository {

    private static final RowMapper<Note> NOTE_ROW_MAPPER = (rs, rowNum) -> new Note(
            rs.getLong("id"),
            rs.getString("title"),
            rs.getString("body")
    );

    private final JdbcTemplate jdbcTemplate;
    private final NamedParameterJdbcTemplate namedParameterJdbcTemplate;

    public NoteRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
        this.namedParameterJdbcTemplate = new NamedParameterJdbcTemplate(jdbcTemplate);
    }

    public Note createNote(Note note) {
        String sql = "INSERT INTO notes (title, body) VALUES (:title, :body)";
        MapSqlParameterSource params = new MapSqlParameterSource()
                .addValue("title", note.getTitle())
                .addValue("body", note.getBody());

        KeyHolder keyHolder = new GeneratedKeyHolder();
        namedParameterJdbcTemplate.update(sql, params, keyHolder, new String[]{"id"});

        long id = keyHolder.getKey().longValue();
        return new Note(id, note.getTitle(), note.getBody());
    }

    public Note getById(long id) {
        String sql = "SELECT id, title, body FROM notes WHERE id = :id";
        MapSqlParameterSource params = new MapSqlParameterSource()
                .addValue("id", id);
        try {
            return namedParameterJdbcTemplate.queryForObject(sql, params, NOTE_ROW_MAPPER);
        } catch (Exception e) {
            return null;
        }
    }

    public List<Note> getAll() {
        String sql = "SELECT id, title, body FROM notes";
        return jdbcTemplate.query(sql, NOTE_ROW_MAPPER);
    }

    public int updateNote(Note note) {
        String sql = "UPDATE notes SET title = :title, body = :body WHERE id = :id";
        MapSqlParameterSource params = new MapSqlParameterSource()
                .addValue("title", note.getTitle())
                .addValue("body", note.getBody())
                .addValue("id", note.getId());
        return namedParameterJdbcTemplate.update(sql, params);
    }

    public int deleteNote(long id) {
        String sql = "DELETE FROM notes WHERE id = :id";
        MapSqlParameterSource params = new MapSqlParameterSource()
                .addValue("id", id);
        return namedParameterJdbcTemplate.update(sql, params);
    }
}
