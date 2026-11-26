package app.notes_api.exception;

/**
 * Custom exception class representing a resource not found error.
 * Extends RuntimeException to indicate an unchecked exception.
 */
public class ResourceNotFoundException extends RuntimeException {

    /**
     * Constructs a new ResourceNotFoundException with the specified detail message.
     *
     * @param message the detail message
     */
    public ResourceNotFoundException(String message) {
        super(message);
    }
}
