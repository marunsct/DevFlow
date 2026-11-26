package app.notes_api.service

import app.notes_api.exception.ResourceNotFoundException
import app.notes_api.model.Note
import app.notes_api.repository.*
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional

@Service
class NoteService(private val noteRepository: NoteRepository) {

    @Transactional(readOnly = true)
    fun getById(id: Long): Note =
        noteRepository.findById(id) ?: throw ResourceNotFoundException("Note with id $id not found")

    @Transactional(readOnly = true)
    fun getAll(): List<Note> = noteRepository.findAll()
}
