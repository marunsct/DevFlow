package app.notes_api.repository

import app.notes_api.model.Note
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.jdbc.core.RowMapper
import org.springframework.stereotype.Repository

@Repository
class NoteRepository(private val jdbcTemplate: JdbcTemplate) {

    private val noteRowMapper = RowMapper<Note> { rs, _ ->
        Note(rs.getLong("id"), rs.getString("title"), rs.getString("body"))
    }

    fun findAll(): List<Note> = jdbcTemplate.query("SELECT id, title, body FROM notes ORDER BY id", noteRowMapper)

    fun findById(id: Long): Note? =
        jdbcTemplate.query("SELECT id, title, body FROM notes WHERE id = ?", noteRowMapper, id).firstOrNull()
}
